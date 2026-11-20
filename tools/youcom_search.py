from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .common import YouComClient, YouComError, credential_key
from .formatters import format_search
from .messages import emit, emit_error
from .payloads import build_search_body, search_timeout


class YouComSearchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = YouComClient(credential_key(self.runtime.credentials))
            body = build_search_body(tool_parameters)
            payload = client.search(body, timeout=search_timeout(body))
        except YouComError as exc:
            yield from emit_error(self, exc)
            return
        yield from emit(self, payload, format_search(payload))
