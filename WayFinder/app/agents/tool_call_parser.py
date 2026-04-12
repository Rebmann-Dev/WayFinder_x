import json
import re
from typing import Any

_TOOL_CALL_BLOCK = re.compile(
    r"<tool_call>\s*([\s\S]*?)\s*</tool_call>",
    re.IGNORECASE,
)


def parse_tool_calls(assistant_text: str) -> list[dict[str, Any]]:
    """Extract tool call dicts from Qwen-style `<tool_call>...</tool_call>` blocks."""
    calls: list[dict[str, Any]] = []
    for m in _TOOL_CALL_BLOCK.finditer(assistant_text):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "name" in obj:
            calls.append(obj)
    return calls


def normalize_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
