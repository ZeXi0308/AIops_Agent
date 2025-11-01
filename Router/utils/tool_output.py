from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Pattern, Tuple

# --- Type & Handler Definitions -----------------------------------------------

TextHandler = Callable[[str], Tuple[str, List[Dict[str, str]]]]


def _normalise_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (bytes, bytearray)):
        try:
            return content.decode()
        except Exception:
            return str(content)
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    return str(content)


_DATA_URL_RE = re.compile(
    r"data:(?P<mime>image/[\w.+-]+);base64,(?P<data>[A-Za-z0-9+/=\r\n]+)",
    re.IGNORECASE,
)


def _handle_strip_base64(text: str) -> Tuple[str, List[Dict[str, str]]]:
    images: List[Dict[str, str]] = []

    def _repl(match: re.Match[str]) -> str:
        images.append({"mime": match.group("mime"), "data": match.group("data")})
        return ""

    cleaned = _DATA_URL_RE.sub(_repl, text or "")
    if not cleaned.strip() and images:
        cleaned = "An image or chart has been generated."
    return cleaned.strip(), images


def _handle_plain_text(text: str) -> Tuple[str, List[Dict[str, str]]]:
    return text, []


def _handle_suppress(text: str) -> Tuple[str, List[Dict[str, str]]]:
    return "", []


# --- Policies & Mappings ------------------------------------------------------

TEXT_HANDLERS: Dict[str, TextHandler] = {
    "plain_text": _handle_plain_text,
    "strip_base64": _handle_strip_base64,
    "suppress": _handle_suppress,
}

DEFAULT_POLICY: Dict[str, str] = {
    "text_handler": "plain_text",
    "summary_handler": "llm_default",
    "log_bucket": "Tool Message",
}


def _merge_policy(overrides: Dict[str, str]) -> Dict[str, str]:
    policy = DEFAULT_POLICY.copy()
    policy.update(overrides)
    return policy


def _normalise_tool_name(tool_name: str) -> str:
    return re.sub(r"[\s:-]+", "_", tool_name.strip()).lower()


IMAGE_TOOL_POLICY = _merge_policy({
    "text_handler": "strip_base64",
    "summary_handler": "none",
    "log_bucket": "Tool Images",
})

SILENT_TOOL_POLICY = _merge_policy({
    "text_handler": "suppress",
    "summary_handler": "none",
})

MCP_POLICIES: Dict[str, Dict[str, str]] = {
    "generate_line_chart": IMAGE_TOOL_POLICY,
    "chartrenderer": IMAGE_TOOL_POLICY,
    "get_mcp_config_diagram": _merge_policy({"summary_handler": "none"}),
    "internal_logging_tool": SILENT_TOOL_POLICY,
}

MCP_POLICY_PATTERNS: List[Tuple[Pattern[str], Dict[str, str]]] = [
    (
        re.compile(r"^(generate|render)_[\w-]+_(chart|map|diagram|graph)$"),
        IMAGE_TOOL_POLICY,
    ),
    (
        re.compile(r"^[\w-]*chart[\w-]*renderer$"),
        IMAGE_TOOL_POLICY,
    ),
    (
        re.compile(r"^gpt[\w-]*vis"),
        IMAGE_TOOL_POLICY,
    ),
]


def get_policy(tool_name: str | None) -> Dict[str, str]:
    if not tool_name:
        return DEFAULT_POLICY.copy()

    normalised = _normalise_tool_name(tool_name)
    if normalised in MCP_POLICIES:
        return MCP_POLICIES[normalised].copy()

    for pattern, policy in MCP_POLICY_PATTERNS:
        if pattern.match(normalised):
            return policy.copy()

    return DEFAULT_POLICY.copy()


# --- Public API for Router ----------------------------------------------------

def process_tool_message(
    tool_name: str | None, content: Any
) -> Tuple[str, List[Dict[str, str]], str]:
    """
    Processes raw tool content based on the configured policy for that tool.

    Args:
        tool_name: The name of the tool (server_id) that was executed.
        content: The raw output from the tool.

    Returns:
        A tuple of (cleaned_text, images_list, log_bucket_name).
    """
    policy = get_policy(tool_name)
    handler_name = policy.get("text_handler", "plain_text")
    handler = TEXT_HANDLERS.get(handler_name, _handle_plain_text)

    normalised_text = _normalise_content(content)
    cleaned_text, images = handler(normalised_text)

    log_bucket = policy.get("log_bucket", "Tool Message")

    return cleaned_text, images, log_bucket


def get_summary_strategy(tool_name: str | None) -> str:
    """
    Retrieves the summarization strategy (e.g., 'none', 'llm_default') for a tool.
    """
    policy = get_policy(tool_name)
    return policy.get("summary_handler", "llm_default")


def sanitise_text_field(text: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    General-purpose utility to remove embedded Base64 images from any free-text field.
    """
    if not text:
        return "", []
    return _handle_strip_base64(text)
