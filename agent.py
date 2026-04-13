import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
import zoneinfo

import groq
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama

from tools.finance_tools import get_stock_info
from tools.notion_tools import add_content_to_page, create_notion_page, search_notion
from user_state import get_history, get_timezone, save_message

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()


def _build_system_prompt(user_id: str = "") -> str:
    parent_id = os.environ.get("NOTION_PARENT_PAGE_ID", "")
    tz_name = get_timezone(user_id) if user_id else os.environ.get("TZ", "Asia/Manila")
    tz = zoneinfo.ZoneInfo(tz_name)
    now = datetime.now(tz).strftime("%A, %B %d, %Y %I:%M %p")
    prompt = _PROMPT_TEMPLATE.replace("{{NOTION_PARENT_PAGE_ID}}", parent_id)
    prompt = prompt.replace("{{CURRENT_TIME}}", now)
    prompt = prompt.replace("{{TIMEZONE}}", tz_name)
    return prompt

_tools: list[BaseTool] | None = None
_tools_by_name: dict[str, BaseTool] | None = None
_tool_defs: list[dict[str, Any]] | None = None


def _make_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient({
        "notion": {
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": {
                "OPENAPI_MCP_HEADERS": json.dumps({
                    "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
                    "Notion-Version": "2025-09-03",
                })
            },
            "transport": "stdio",
        }
    })


def _relax_array_item_types(obj: dict | list) -> None:
    """Remove type constraints from array items so Groq accepts objects.

    MCP tool schemas define fields like ``children`` as ``string[]``
    (expecting JSON-encoded block strings), but LLMs naturally produce
    objects.  Relaxing the schema lets Groq's server-side validation pass.
    """
    if isinstance(obj, dict):
        if obj.get("type") == "array" and isinstance(obj.get("items"), dict):
            obj["items"].pop("type", None)
        for value in obj.values():
            if isinstance(value, (dict, list)):
                _relax_array_item_types(value)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _relax_array_item_types(item)


# Notion ID fields that must be valid UUIDs with dashes.
_UUID_FIELDS = {"page_id", "database_id", "data_source_id", "block_id"}
_BARE_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


def _format_uuid(value: str) -> str:
    """Insert dashes into a bare 32-char hex ID to make it a valid UUID."""
    if _BARE_HEX_RE.match(value):
        return str(uuid.UUID(value))
    return value


def _fix_args(args: dict) -> dict:
    """Fix bare-hex UUIDs in tool arguments."""
    result: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, dict):
            result[key] = _fix_args(value)
        elif isinstance(value, list):
            result[key] = [
                _fix_args(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif key in _UUID_FIELDS and isinstance(value, str):
            result[key] = _format_uuid(value)
        else:
            result[key] = value
    return result


# Simple tools that work reliably with any LLM
_SIMPLE_TOOLS = [create_notion_page, search_notion, add_content_to_page, get_stock_info]


async def init_agent() -> None:
    """Fetch tool definitions from the Notion MCP server. Call once at startup."""
    global _tools, _tools_by_name, _tool_defs

    provider = os.environ.get("LLM_PROVIDER", "ollama")

    if provider == "groq":
        # Groq can handle the full MCP tool set
        client = _make_mcp_client()
        notion_mcp_tools = await client.get_tools()
        _tools = _SIMPLE_TOOLS + notion_mcp_tools
    else:
        # Smaller local models choke on 20+ tool defs — only expose simple tools
        _tools = list(_SIMPLE_TOOLS)

    _tools_by_name = {t.name: t for t in _tools}

    _tool_defs = [convert_to_openai_tool(t) for t in _tools]
    for td in _tool_defs:
        _relax_array_item_types(td)

    log.info("Loaded %d tools: %s", len(_tools), list(_tools_by_name.keys()))


def _create_llm():
    """Create the LLM instance based on the configured provider."""
    provider = os.environ.get("LLM_PROVIDER", "ollama")
    if provider == "groq":
        model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        return ChatGroq(model=model, temperature=0)
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    return ChatOllama(model=model, temperature=0)


def _build_messages(user_message: str, user_id: str) -> list[BaseMessage]:
    """Build the initial message list with system prompt, history, and user message."""
    messages: list[BaseMessage] = [SystemMessage(content=_build_system_prompt(user_id))]

    if user_id:
        for msg in get_history(user_id):
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        save_message(user_id, "user", user_message)

    messages.append(HumanMessage(content=user_message))
    return messages


async def _invoke_tool(tc: ToolCall) -> tuple[str, str | None]:
    """Invoke a single tool call. Returns (result_str, error_or_none)."""
    assert _tools_by_name is not None
    tool_fn = _tools_by_name.get(tc["name"])
    if not tool_fn:
        log.warning("Unknown tool requested: %s", tc["name"])
        return f"Unknown tool: {tc['name']}", None

    fixed_args = _fix_args(tc["args"])
    log.info("Calling tool %s with args %s", tc["name"], fixed_args)
    try:
        result = await tool_fn.ainvoke(fixed_args)
        log.debug("Tool %s returned %d chars", tc["name"], len(str(result)))
        return str(result), None
    except Exception as exc:
        log.exception("Tool %s raised an error", tc["name"])
        return f"Tool error for {tc['name']}: {exc}", None


def _check_repeated_error(result_str: str, last_error: str | None) -> tuple[str, str | None]:
    """Detect repeated errors and nudge the model. Returns (result_str, updated_last_error)."""
    if "error" not in result_str.lower():
        return result_str, last_error
    if result_str == last_error:
        log.warning("Repeated error detected, nudging model")
        result_str += (
            "\n\nYou already got this exact error. Do NOT retry the same "
            "approach. Try different parameters, or explain to the user "
            "what went wrong."
        )
    return result_str, result_str


def _save_reply(user_id: str, reply: str) -> None:
    if user_id:
        save_message(user_id, "assistant", reply)


async def run_agent(user_message: str, user_id: str = "", max_iterations: int = 10) -> str:
    if _tools is None or _tools_by_name is None or _tool_defs is None:
        await init_agent()

    assert _tools is not None
    assert _tools_by_name is not None
    assert _tool_defs is not None

    llm_with_tools = _create_llm().bind_tools(_tool_defs)
    messages = _build_messages(user_message, user_id)

    log.debug("Message chain (%d messages):", len(messages))
    for i, m in enumerate(messages):
        log.debug("  [%d] %s: %s", i, type(m).__name__, str(m.content)[:200])

    last_error: str | None = None
    tools_called = False
    for iteration in range(max_iterations):
        try:
            response = await llm_with_tools.ainvoke(messages)
        except groq.RateLimitError as exc:
            log.warning("Groq rate limit hit: %s", exc)
            return (
                "I'm temporarily rate-limited by the AI provider. "
                "Please try again in a few minutes."
            )
        messages.append(response)

        if not response.tool_calls:
            log.info("Agent finished after %d iteration(s) with no tool calls", iteration + 1)
            log.debug("Response content: %s", str(response.content)[:500])
            reply = str(response.content) if response.content else "Done."
            # Only save to history if the model actually used tools, or if
            # this was a simple conversational reply (iteration 0, no action needed).
            # Skip saving when the model claims it did something but never called tools.
            if tools_called or iteration == 0:
                _save_reply(user_id, reply)
            else:
                log.warning("Not saving reply — model claimed action without calling tools")
            return reply

        tools_called = True
        for tc in response.tool_calls:
            result_str, _ = await _invoke_tool(tc)
            result_str, last_error = _check_repeated_error(result_str, last_error)
            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

    log.warning("Agent hit max iterations (%d)", max_iterations)
    fallback = "I've completed all the steps I could. Check Notion for any created content."
    _save_reply(user_id, fallback)
    return fallback
