import logging
import re
import uuid
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.tools import BaseTool

log = logging.getLogger(__name__)

# Notion ID fields that must be valid UUIDs with dashes.
_UUID_FIELDS = {"page_id", "database_id", "data_source_id", "block_id"}
_BARE_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


def _format_uuid(value: str) -> str:
    """Insert dashes into a bare 32-char hex ID to make it a valid UUID."""
    if _BARE_HEX_RE.match(value):
        return str(uuid.UUID(value))
    return value


def fix_args(args: dict) -> dict:
    """Fix bare-hex UUIDs in tool arguments."""
    result: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, dict):
            result[key] = fix_args(value)
        elif isinstance(value, list):
            result[key] = [
                fix_args(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif key in _UUID_FIELDS and isinstance(value, str):
            result[key] = _format_uuid(value)
        else:
            result[key] = value
    return result


async def invoke_tool(
    tc: ToolCall, tools_by_name: dict[str, BaseTool],
) -> str:
    """Invoke a single tool call. Returns the result string."""
    tool_fn = tools_by_name.get(tc["name"])
    if not tool_fn:
        log.warning("Unknown tool requested: %s", tc["name"])
        return f"Unknown tool: {tc['name']}"

    fixed_args = fix_args(tc["args"])
    log.info("Calling tool %s with args %s", tc["name"], fixed_args)
    try:
        result = await tool_fn.ainvoke(fixed_args)
        log.debug("Tool %s returned %d chars", tc["name"], len(str(result)))
        return str(result)
    except Exception as exc:
        log.exception("Tool %s raised an error", tc["name"])
        return f"Tool error for {tc['name']}: {exc}"


def check_repeated_error(
    result_str: str, last_error: str | None,
) -> tuple[str, str | None]:
    """Detect repeated errors and nudge the model."""
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


async def process_tool_calls(
    tool_calls: list,
    messages: list[BaseMessage],
    last_error: str | None,
    tools_by_name: dict[str, BaseTool],
) -> str | None:
    """Execute tool calls and append results to messages. Returns updated last_error."""
    for tc in tool_calls:
        result_str = await invoke_tool(tc, tools_by_name)
        result_str, last_error = check_repeated_error(result_str, last_error)
        messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))
    return last_error
