import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .common import YouComClient, YouComError, credential_key
from .formatters import format_research
from .messages import emit, emit_error
from .payloads import build_research_body, frontier_wait_seconds, research_read_timeout


class YouComResearchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = YouComClient(credential_key(self.runtime.credentials))
            body = build_research_body(tool_parameters)
            payload = run_research(client, body, frontier_wait_seconds(tool_parameters))
        except YouComError as exc:
            yield from emit_error(self, exc)
            return
        yield from emit(self, payload, format_research(payload))


def run_research(
    client: YouComClient,
    body: dict[str, Any],
    max_wait_seconds: int,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> dict[str, Any]:
    effort = str(body.get("research_effort") or "standard")
    if effort != "frontier":
        return client.research(body, timeout=research_read_timeout(effort))

    # frontier is rejected unless background is true, and it can run for hours.
    submitted = client.research({**body, "background": True}, timeout=60)
    task_id = str(submitted.get("task_id") or "")
    if not task_id:
        raise YouComError("You.com did not return a task id for the frontier research request.")
    deadline = monotonic() + max_wait_seconds
    latest = submitted
    while monotonic() < deadline:
        latest = client.research_task(task_id, timeout=30)
        status = str(latest.get("status") or "")
        if status == "completed" and isinstance(latest.get("result"), dict):
            return latest["result"]
        if status == "failed":
            raise YouComError(str(latest.get("error") or "The frontier research task failed."))
        if status == "cancelled":
            raise YouComError("The frontier research task was cancelled.")
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(2.0, remaining))
    return {
        "incomplete": True,
        "status": latest.get("status") or submitted.get("status"),
        "task_id": task_id,
        "task": latest,
    }
