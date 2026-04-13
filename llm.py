import json
import logging
import os
from typing import Any

import groq
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama

from config import cfg

log = logging.getLogger(__name__)


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
    """Remove type constraints from array items so Groq accepts objects."""
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


def create_llm() -> ChatGroq | ChatOllama:
    """Create the LLM instance based on the configured provider."""
    if cfg.llm_provider == "groq":
        return ChatGroq(model=cfg.groq_model, temperature=cfg.groq_temperature)
    return ChatOllama(model=cfg.ollama_model, temperature=cfg.ollama_temperature)


async def load_tools(simple_tools: list[BaseTool]) -> tuple[
    list[BaseTool], dict[str, BaseTool], list[dict[str, Any]]
]:
    """Load and prepare tool definitions. Returns (tools, tools_by_name, tool_defs)."""
    if cfg.llm_provider == "groq":
        client = _make_mcp_client()
        notion_mcp_tools = await client.get_tools()
        tools = simple_tools + notion_mcp_tools
    else:
        tools = list(simple_tools)

    tools_by_name = {t.name: t for t in tools}

    tool_defs = [convert_to_openai_tool(t) for t in tools]
    for td in tool_defs:
        _relax_array_item_types(td)

    log.info("Loaded %d tools: %s", len(tools), list(tools_by_name.keys()))
    return tools, tools_by_name, tool_defs


async def invoke_llm(llm_with_tools, messages: list[BaseMessage]) -> AIMessage | None:
    """Invoke the LLM, returning None on rate limit."""
    try:
        return await llm_with_tools.ainvoke(messages)
    except groq.RateLimitError as exc:
        log.warning("Groq rate limit hit: %s", exc)
        return None
