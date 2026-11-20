"""Shared invoke wrapper. Success returns JSON first, then text, matching Dify agent and workflow use."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from .common import YouComError


def emit(
    tool: Any,
    payload: dict[str, Any],
    text: str,
) -> Generator[ToolInvokeMessage, None, None]:
    yield tool.create_json_message(payload)
    yield tool.create_text_message(text)


def emit_error(tool: Any, error: YouComError) -> Generator[ToolInvokeMessage, None, None]:
    message = str(error)
    yield tool.create_text_message(message)
    yield tool.create_json_message(
        {"ok": False, **error.to_dict()}
    )
