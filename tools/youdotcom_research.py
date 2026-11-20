import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .common import YouComClient, YouComError, credential_key, require_text, unset
from .formatters import format_research
from .messages import emit, emit_error
from .payloads import build_research_body, frontier_wait_seconds, research_read_timeout


class YouComResearchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = YouComClient(credential_key(self.runtime.credentials))
            raw_task_id = tool_parameters.get("task_id")
            task_id = None if unset(raw_task_id) else require_text(raw_task_id, "task_id")
            body = {} if task_id else build_research_body(tool_parameters)
            payload = run_research(
                client, body, frontier_wait_seconds(tool_parameters), task_id=task_id
            )
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
    task_id: str | None = None,
) -> dict[str, Any]:
    effort = str(body.get("research_effort") or "standard")
    if not task_id and effort != "frontier":
        return client.research(body, timeout=research_read_timeout(effort))

    # frontier is rejected unless background is true, and it can run for hours.
    if task_id:
        submitted = {"task_id": task_id}
    else:
        submitted = client.research({**body, "background": True}, timeout=60)
        task_id = str(submitted.get("task_id") or "")
        if not task_id:
            raise YouComError("You.com did not return a task id for the frontier research request.")
    deadline = monotonic() + max_wait_seconds
    latest = submitted
    try:
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            latest = client.research_task(task_id, timeout=min(30.0, remaining))
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
    except YouComError as exc:
        raise YouComError(
            f"{exc} Task id: {task_id}. Supply task_id to check this task without resubmitting.",
            status_code=exc.status_code,
            details={**exc.details, "task_id": task_id, "task": latest},
        ) from exc
    return {
        "incomplete": True,
        "status": latest.get("status") or submitted.get("status"),
        "task_id": task_id,
        "task": latest,
    }
