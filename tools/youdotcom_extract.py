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
                    result = client.extract(body, timeout=timeout)
                    results.append({**result, "url": result.get("url") or url})
                except YouComError as exc:
                    errors.append({"url": url, **exc.to_dict()})
                    if exc.status_code in {401, 402, 429}:
                        break
            payload = {
                "endpoint": "https://ydc-index.io/v1/extract",
                "results": results,
                "errors": errors,
            }
            if not results:
                detail = "; ".join(item["error"] for item in errors) or "No page content was returned."
                primary = next(
                    (item for item in errors if item["status_code"] in {401, 402, 429}),
                    errors[0] if errors else {},
                )
                raise YouComError(detail, status_code=primary.get("status_code"), details=payload)
        except YouComError as exc:
            yield from emit_error(self, exc)
            return
        yield from emit(self, payload, format_extract(payload))
