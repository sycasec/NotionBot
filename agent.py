import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import zoneinfo

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from config import cfg
from llm import create_llm, invoke_llm, load_tools
from tool_utils import process_tool_calls
from tools.date_tools import date_math
from tools.finance_tools import get_stock_info
from tools.notion_tools import add_content_to_page, create_notion_page, search_notion
from tools.search_tools import web_search
from tools.weather_tools import get_weather
from user_state import get_history, get_timezone, save_message

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(user_id: str = "") -> str:
    parent_id = cfg.notion_parent_page_id
    tz_name = get_timezone(user_id) if user_id else cfg.default_timezone
    tz = zoneinfo.ZoneInfo(tz_name)
    now = datetime.now(tz).strftime("%A, %B %d, %Y %I:%M %p")
    prompt = _PROMPT_TEMPLATE.replace("{{NOTION_PARENT_PAGE_ID}}", parent_id)
    prompt = prompt.replace("{{CURRENT_TIME}}", now)
    prompt = prompt.replace("{{TIMEZONE}}", tz_name)
    return prompt


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@dataclass
class _ToolRegistry:
    tools: list[BaseTool] = field(default_factory=list)
    by_name: dict[str, BaseTool] = field(default_factory=dict)
    defs: list[dict[str, Any]] = field(default_factory=list)
    loaded: bool = False

_registry = _ToolRegistry()

_SIMPLE_TOOLS = [
    create_notion_page,
    search_notion,
    add_content_to_page,
    get_stock_info,
    get_weather,
    web_search,
    date_math,
]


async def init_agent() -> None:
    """Load tool definitions. Call once at startup."""
    tools, by_name, defs = await load_tools(_SIMPLE_TOOLS)
    _registry.tools = tools
    _registry.by_name = by_name
    _registry.defs = defs
    _registry.loaded = True


async def _ensure_initialized() -> None:
    if not _registry.loaded:
        await init_agent()


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return len(text) // 4


def _build_messages(user_message: str, user_id: str) -> list[BaseMessage]:
    """Build the initial message list with system prompt, history, and user message."""
    system_prompt = _build_system_prompt(user_id)
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]

    used_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_message) + 512
    budget = cfg.max_history_tokens

    if user_id:
        history = get_history(user_id)
        selected: list[BaseMessage] = []
        for msg in reversed(history):
            msg_tokens = _estimate_tokens(msg["content"])
            if used_tokens + msg_tokens > budget:
                break
            used_tokens += msg_tokens
            if msg["role"] == "user":
                selected.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                selected.append(AIMessage(content=msg["content"]))

        selected.reverse()
        messages.extend(selected)
        log.debug(
            "History: %d/%d messages fit within %d token budget (%d used)",
            len(selected), len(history), budget, used_tokens,
        )
        save_message(user_id, "user", user_message)

    messages.append(HumanMessage(content=user_message))
    return messages


# ---------------------------------------------------------------------------
# Fake-action detection
# ---------------------------------------------------------------------------

_ACTION_WORDS = re.compile(
    r"\b(created|added|appended|updated|modified|searched|deleted|removed|wrote)\b",
    re.IGNORECASE,
)

_NUDGE_MESSAGE = (
    "You did NOT actually call any tools. You MUST use the "
    "appropriate tool to perform the action. Do not describe "
    "what you would do — actually call the tool now."
)


def _looks_like_faked_action(content: str) -> bool:
    return bool(_ACTION_WORDS.search(content))


def _should_retry_fake(reply: str, tools_called: bool, fake_retries: int) -> bool:
    return (
        not tools_called
        and _looks_like_faked_action(reply)
        and fake_retries < cfg.max_retries_on_fake
    )


def _save_reply(user_id: str, reply: str) -> None:
    if user_id:
        save_message(user_id, "assistant", reply)


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def _log_message_chain(messages: list[BaseMessage]) -> None:
    if not log.isEnabledFor(logging.DEBUG):
        return
    log.debug("Message chain (%d messages):", len(messages))
    for i, m in enumerate(messages):
        log.debug("  [%d] %s: %s", i, type(m).__name__, str(m.content)[:200])


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

async def run_agent(user_message: str, user_id: str = "", max_iterations: int = 0) -> str:
    if max_iterations <= 0:
        max_iterations = cfg.max_iterations

    await _ensure_initialized()

    llm_with_tools = create_llm().bind_tools(_registry.defs)
    messages = _build_messages(user_message, user_id)
    _log_message_chain(messages)

    last_error: str | None = None
    tools_called = False
    fake_retries = 0
    for iteration in range(max_iterations):
        response = await invoke_llm(llm_with_tools, messages)
        if response is None:
            return "I'm temporarily rate-limited by the AI provider. Please try again in a few minutes."
        messages.append(response)

        if response.tool_calls:
            tools_called = True
            last_error = await process_tool_calls(
                response.tool_calls, messages, last_error, _registry.by_name,
            )
            continue

        reply = str(response.content) if response.content else "Done."

        if _should_retry_fake(reply, tools_called, fake_retries):
            fake_retries += 1
            log.warning("Faked action detected (retry %d/%d), nudging", fake_retries, cfg.max_retries_on_fake)
            messages.pop()
            messages.append(HumanMessage(content=_NUDGE_MESSAGE))
            continue

        log.info("Agent finished after %d iteration(s)", iteration + 1)
        if not _looks_like_faked_action(reply) or tools_called:
            _save_reply(user_id, reply)
        return reply

    log.warning("Agent hit max iterations (%d)", max_iterations)
    fallback = "I've completed all the steps I could. Check Notion for any created content."
    _save_reply(user_id, fallback)
    return fallback
