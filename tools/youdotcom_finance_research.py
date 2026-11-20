from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .common import YouComClient, YouComError, credential_key
from .formatters import format_research
from .messages import emit, emit_error
from .payloads import build_finance_body, finance_read_timeout


class YouComFinanceResearchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = YouComClient(credential_key(self.runtime.credentials))
            body = build_finance_body(tool_parameters)
            payload = client.finance_research(body, timeout=finance_read_timeout(body["research_effort"]))
        except YouComError as exc:
            yield from emit_error(self, exc)
            return
        yield from emit(self, payload, format_research(payload))
