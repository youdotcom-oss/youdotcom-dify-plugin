from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .common import YouComClient, YouComError, credential_key
from .formatters import format_extract
from .messages import emit, emit_error
from .payloads import build_extract_calls


class YouComExtractTool(Tool):
    """Fetches one or more pages through POST /v1/extract, one URL per request."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = YouComClient(credential_key(self.runtime.credentials))
            calls = build_extract_calls(tool_parameters)
            results: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            for url, body, timeout in calls:
                try:
                    results.append(client.extract(body, timeout=timeout))
                except YouComError as exc:
                    if exc.status_code in {401, 429}:
                        raise
                    errors.append({"url": url, "error": str(exc), "status_code": exc.status_code})
            if not results:
                detail = "; ".join(item["error"] for item in errors) or "No page content was returned."
                raise YouComError(detail, status_code=errors[0]["status_code"] if errors else None)
            payload = {
                "endpoint": "https://ydc-index.io/v1/extract",
                "results": results,
                "errors": errors,
            }
        except YouComError as exc:
            yield from emit_error(self, exc)
            return
        yield from emit(self, payload, format_extract(payload))
