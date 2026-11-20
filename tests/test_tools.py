import json
from pathlib import Path

import pytest
import requests
import yaml
from dify_plugin.entities.tool import ToolConfiguration

from tools.common import YouComError
from tools.youdotcom_answer import YouComAnswerTool
from tools.youdotcom_extract import YouComExtractTool
from tools.youdotcom_finance_research import YouComFinanceResearchTool
from tools.youdotcom_research import YouComResearchTool, run_research
from tools.youdotcom_search import YouComSearchTool
from tools.formatters import format_search


class RecordingClient:
    def __init__(self, api_key, session=None):
        self.api_key = api_key
        self.calls = []
        self.search_payload = {
            "results": {
                "web": [
                    {
                        "url": "https://news.example/story",
                        "title": "Story",
                        "snippets": ["A news snippet"],
                        "description": "Desk copy",
                    }
                ]
            },
            "metadata": {"query": "headlines"},
        }
        self.extract_payload = {
            "url": "https://example.com",
            "title": "Example",
            "contents": {"full_page": {"markdown": "Hello page"}},
        }

    def search(self, body, timeout):
        self.calls.append(("search", body, timeout))
        return self.search_payload

    def extract(self, body, timeout):
        self.calls.append(("extract", body, timeout))
        if "missing" in body["url"]:
            raise YouComError("page failed", status_code=502)
        return {**self.extract_payload, "url": body["url"]}

    def answer(self, body, timeout):
        self.calls.append(("answer", body, timeout))
        return {
            "answer": "Cited answer [1].",
            "citations": [{"source": "https://example.com", "excerpts": ["Quoted line"]}],
            "results": {"web": []},
        }

    def finance_research(self, body, timeout):
        self.calls.append(("finance", body, timeout))
        return {
            "output": {
                "content": "Revenue was higher [1].",
                "content_type": "text",
                "sources": [{"url": "https://sec.example/10q", "title": "10-Q"}],
            },
            "warnings": [],
        }


def _install(monkeypatch, module, client):
    monkeypatch.setattr(module + ".YouComClient", lambda api_key: client)


def _json(message):
    return message.message.json_object


def _text(message):
    return message.message.text


def _messages(tool_cls, parameters, credentials=None):
    creds = {"youdotcom_api_key": "secret-key"} if credentials is None else credentials
    return list(tool_cls.from_credentials(creds).invoke(parameters))


def test_search_returns_json_then_text(monkeypatch):
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youdotcom_search", client)
    messages = _messages(YouComSearchTool, {"query": "headlines", "count": 2})
    assert [message.type.value for message in messages] == ["json", "text"]
    assert _json(messages[0])["results"]["web"][0]["url"].endswith("/story")
    assert "Story" in _text(messages[1])
    assert "news intent" in messages[1].message.text
    assert client.calls[0][0] == "search"
    assert client.calls[0][1]["count"] == 2


@pytest.mark.parametrize("use_dify_defaults", [True, False])
def test_search_requests_highlights_and_core_knowledge_by_default(monkeypatch, use_dify_defaults):
    defaults = {}
    if use_dify_defaults:
        definition = ToolConfiguration.model_validate(yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "tools" / "youdotcom_search.yaml").read_text()
        ))
        defaults = {
            parameter.name: parameter.default
            for parameter in definition.parameters
            if parameter.default is not None
        }
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youdotcom_search", client)
    _messages(YouComSearchTool, {**defaults, "query": "headlines"})

    assert {
        key: client.calls[0][1].get(key) for key in ("count", "extraction", "knowledge")
    } == {"count": 10, "extraction": {"extraction_mode": "highlights"}, "knowledge": "core"}


@pytest.mark.parametrize("mode", ["none", "highlights", "full_page"])
@pytest.mark.parametrize("source", ["blend", "cache", "fetch"])
def test_search_accepts_dify_defaults_for_each_extraction_mode(monkeypatch, mode, source):
    definition = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "tools" / "youdotcom_search.yaml").read_text()
    )
    defaults = {
        parameter["name"]: parameter["default"]
        for parameter in definition["parameters"]
        if "default" in parameter
    }
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youdotcom_search", client)
    messages = _messages(
        YouComSearchTool,
        {**defaults, "query": "headlines", "extraction_mode": mode, "extraction_source": source,
         "knowledge": "off"},
    )

    assert [message.type.value for message in messages] == ["json", "text"]
    body = client.calls[0][1]
    assert "knowledge" not in body
    if mode == "none":
        assert "extraction" not in body
    elif mode == "highlights":
        assert body["extraction"] == {"extraction_mode": "highlights"}
    else:
        assert body["extraction"] == {
            "extraction_mode": "full_page",
            "extraction_source": source,
            "full_page": {"extraction_formats": ["markdown"]},
        }


def test_extract_continues_after_a_page_error_and_stops_on_401(monkeypatch):
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youdotcom_extract", client)
    messages = _messages(
        YouComExtractTool,
        {"urls": "https://example.com/ok, https://example.com/missing"},
    )
    assert messages[0].type.value == "json"
    assert len(_json(messages[0])["results"]) == 1
    assert _json(messages[0])["errors"][0]["status_code"] == 502
    assert "Hello page" in _text(messages[1])

    def unauthorized(body, timeout):
        raise YouComError("You.com rejected the API key (401).", status_code=401)

    client.extract = unauthorized
    messages = _messages(YouComExtractTool, {"urls": "https://example.com"})
    assert messages[0].type.value == "text"
    assert "401" in _text(messages[0])
    assert _json(messages[1])["ok"] is False


def test_answer_and_finance_text_include_citations(monkeypatch):
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youdotcom_answer", client)
    messages = _messages(YouComAnswerTool, {"query": "What shipped?"})
    assert _json(messages[0])["answer"].startswith("Cited")
    assert "https://example.com" in _text(messages[1])
    assert client.calls[0][0] == "answer"

    _install(monkeypatch, "tools.youdotcom_finance_research", client)
    messages = _messages(
        YouComFinanceResearchTool,
        {"input": "Latest quarter revenue", "research_effort": "deep"},
    )
    assert _json(messages[0])["output"]["sources"][0]["title"] == "10-Q"
    assert "Revenue was higher" in _text(messages[1])
    assert client.calls[-1][1]["research_effort"] == "deep"
    assert client.calls[-1][2] == 150.0


def test_missing_key_does_not_call_the_api(monkeypatch):
    called = []
    monkeypatch.setattr(
        "tools.youdotcom_search.YouComClient",
        lambda api_key: called.append(api_key),
    )
    messages = list(YouComSearchTool.from_credentials({}).invoke({"query": "x"}))
    assert called == []
    assert "API key is missing" in _text(messages[0])
    assert _json(messages[1])["ok"] is False


def test_frontier_polls_until_complete_or_returns_the_task():
    class ResearchClient:
        def __init__(self):
            self.posts = []
            self.gets = 0

        def research(self, body, timeout):
            self.posts.append(body)
            return {"task_id": "task-9", "status": "queued"}

        def research_task(self, task_id, timeout):
            self.gets += 1
            if self.gets == 1:
                return {"id": task_id, "status": "running", "result": None}
            return {
                "id": task_id,
                "status": "completed",
                "result": {
                    "output": {"content": "Done", "content_type": "text", "sources": []},
                    "warnings": [],
                },
            }

    client = ResearchClient()
    clock = {"now": 0.0}

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        clock["now"] += seconds

    payload = run_research(
        client,
        {"input": "long question", "research_effort": "frontier"},
        max_wait_seconds=30,
        sleep=sleep,
        monotonic=monotonic,
    )
    assert client.posts[0]["background"] is True
    assert payload["output"]["content"] == "Done"

    stalled = ResearchClient()
    stalled.research_task = lambda task_id, timeout: {"id": task_id, "status": "running", "result": None}
    clock["now"] = 0.0
    pending = run_research(
        stalled,
        {"input": "long question", "research_effort": "frontier"},
        max_wait_seconds=3,
        sleep=sleep,
        monotonic=monotonic,
    )
    assert pending["incomplete"] is True
    assert pending["task_id"] == "task-9"


def test_research_tool_uses_standard_by_default(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, api_key):
            self.api_key = api_key

        def research(self, body, timeout):
            seen["body"] = body
            seen["timeout"] = timeout
            return {
                "output": {"content": "Standard note", "content_type": "text", "sources": []},
                "warnings": [],
            }

    monkeypatch.setattr("tools.youdotcom_research.YouComClient", Client)
    messages = _messages(YouComResearchTool, {"input": "Summarize the category"})
    assert seen["body"]["research_effort"] == "standard"
    assert seen["timeout"] == 45.0
    assert messages[0].type.value == "json"
    assert "Standard note" in _text(messages[1])


def test_search_formatter_mentions_empty_results():
    text = format_search({"results": {"web": []}})
    assert "No web or knowledge results" in text


@pytest.mark.parametrize(
    ("tool_name", "parameter_name", "label", "expected"),
    [
        ("search", "country", "Norway (NO)", "NO"),
        ("answer", "country", "Norway (NO)", "NO"),
        ("research", "country", "Norway (NO)", "NO"),
        ("search", "safesearch", "Off", "off"),
        ("answer", "safesearch", "Off", "off"),
        ("search", "knowledge", "Off", "off"),
    ],
)
def test_dify_option_values_survive_yaml_loading(tool_name, parameter_name, label, expected):
    definition = ToolConfiguration.model_validate(yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "tools" / f"youdotcom_{tool_name}.yaml").read_text()
    ))
    parameter = next(item for item in definition.parameters if item.name == parameter_name)
    option = next(item for item in parameter.options if item.label.en_us == label)
    assert option.value == expected


@pytest.mark.parametrize("submission_parameters", [
    {},
    {"input": "", "research_effort": "invalid", "country": "invalid", "output_schema": "invalid"},
])
def test_research_resumes_a_returned_task_without_submitting_again(monkeypatch, submission_parameters):
    class Client:
        def __init__(self):
            self.gets = []

        def research(self, body, timeout):
            pytest.fail("Resuming must not submit another paid task")

        def research_task(self, task_id, timeout):
            self.gets.append(task_id)
            return {
                "status": "completed",
                "result": {"output": {"content": "Resumed report", "sources": []}},
            }

    client = Client()
    _install(monkeypatch, "tools.youdotcom_research", client)
    messages = _messages(YouComResearchTool, {**submission_parameters, "task_id": "task-9"})
    assert messages[0].type.value == "json"
    assert _json(messages[0])["output"]["content"] == "Resumed report"
    assert "Resumed report" in _text(messages[1])
    assert client.gets == ["task-9"]
    definition = ToolConfiguration.model_validate(yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "tools" / "youdotcom_research.yaml").read_text()
    ))
    parameters = {item.name: item for item in definition.parameters}
    assert parameters["task_id"].type.value == "string"
    assert parameters["input"].required is False


@pytest.mark.parametrize("status_code", [429, 500, None])
@pytest.mark.parametrize("resume", [False, True])
def test_research_polling_errors_preserve_task_id(monkeypatch, status_code, resume):
    class Client:
        def research(self, body, timeout):
            return {"task_id": "paid-task", "status": "queued"}

        def research_task(self, task_id, timeout):
            raise YouComError("Polling failed", status_code=status_code)

    _install(monkeypatch, "tools.youdotcom_research", Client())
    parameters = {"task_id": "paid-task"} if resume else {
        "input": "Long question", "research_effort": "frontier",
    }
    messages = _messages(YouComResearchTool, parameters)
    assert messages[0].type.value == "text"
    error = _json(messages[1])
    assert error["ok"] is False
    assert error["status_code"] == status_code
    assert error["task_id"] == "paid-task"
    assert "paid-task" in _text(messages[0])
    assert "task_id" in _text(messages[0])


@pytest.mark.parametrize("max_wait_seconds", [3, 15, 300])
def test_frontier_poll_timeout_never_exceeds_remaining_wait(max_wait_seconds):
    clock = {"now": 0.0}
    timeouts = []

    class Client:
        def research(self, body, timeout):
            return {"task_id": "slow-task", "status": "queued"}

        def research_task(self, task_id, timeout):
            timeouts.append(timeout)
            clock["now"] += timeout
            return {"status": "running"}

    def sleep(seconds):
        clock["now"] += seconds

    payload = run_research(
        Client(), {"input": "Long question", "research_effort": "frontier"},
        max_wait_seconds, sleep=sleep, monotonic=lambda: clock["now"],
    )
    assert payload["incomplete"] is True
    assert payload["task_id"] == "slow-task"
    assert clock["now"] <= max_wait_seconds
    assert all(0 < timeout <= 30 for timeout in timeouts)


@pytest.mark.parametrize("status_code", [401, 429])
def test_extract_retains_completed_pages_when_a_later_call_stops_the_batch(monkeypatch, status_code):
    client = RecordingClient("secret-key")

    def extract(body, timeout):
        client.calls.append(body["url"])
        if body["url"].endswith("/blocked"):
            raise YouComError("Batch stopped", status_code=status_code)
        return {**client.extract_payload, "url": body["url"]}

    client.extract = extract
    _install(monkeypatch, "tools.youdotcom_extract", client)
    messages = _messages(YouComExtractTool, {
        "urls": "https://example.com/ok\nhttps://example.com/blocked\nhttps://example.com/unattempted",
    })
    assert messages[0].type.value == "json"
    payload = _json(messages[0])
    assert payload["results"][0]["url"] == "https://example.com/ok"
    assert payload["errors"][0]["url"] == "https://example.com/blocked"
    assert payload["errors"][0]["status_code"] == status_code
    assert client.calls == ["https://example.com/ok", "https://example.com/blocked"]
    assert "Hello page" in _text(messages[1])


def test_extract_all_failures_keep_each_error_and_a_later_payment_status(monkeypatch):
    def extract(body, timeout):
        payment = body["url"].endswith("/payment")
        raise YouComError(
            "Add credits" if payment else "Site blocked",
            status_code=402 if payment else 502,
            details={"code": "payment_required" if payment else "site_blocked", "retryable": False},
        )

    client = RecordingClient("secret-key")
    client.extract = extract
    _install(monkeypatch, "tools.youdotcom_extract", client)
    messages = _messages(YouComExtractTool, {
        "urls": "https://example.com/blocked\nhttps://example.com/payment",
    })
    assert messages[0].type.value == "text"
    payload = _json(messages[1])
    assert payload["ok"] is False
    assert payload["status_code"] == 402
    assert payload["results"] == []
    assert [error["url"] for error in payload["errors"]] == [
        "https://example.com/blocked", "https://example.com/payment",
    ]
    assert [error["status_code"] for error in payload["errors"]] == [502, 402]
    assert [error["code"] for error in payload["errors"]] == ["site_blocked", "payment_required"]
    assert all(error["retryable"] is False for error in payload["errors"])


@pytest.mark.parametrize("urls", [
    "https://example.com/a,b?q=one,two",
    "https://example.com/a,b?q=one,two,https://example.com/next",
    "https://example.com/a,b?q=one,two,\nhttps://example.com/next",
    ["https://example.com/a,b?q=one,two", "https://example.com/next"],
])
def test_extract_preserves_commas_inside_urls(monkeypatch, urls):
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youdotcom_extract", client)
    messages = _messages(YouComExtractTool, {"urls": urls})
    assert messages[0].type.value == "json"
    results = _json(messages[0])["results"]
    assert results[0]["url"] == "https://example.com/a,b?q=one,two"
    assert len(results) == (1 if urls == "https://example.com/a,b?q=one,two" else 2)


@pytest.mark.parametrize("url", ["https://[", "https://example.com:bad", "https://:80", "file:///tmp/a"])
def test_extract_malformed_urls_return_error_json_without_an_api_call(monkeypatch, url):
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youdotcom_extract", client)
    messages = _messages(YouComExtractTool, {"urls": url})
    assert messages[0].type.value == "text"
    assert _json(messages[1])["ok"] is False
    assert "absolute http or https" in _text(messages[0])
    assert client.calls == []


@pytest.mark.parametrize("response", [{}, {"url": ""}, {"url": None}])
def test_extract_empty_responses_keep_the_requested_url(monkeypatch, response):
    client = RecordingClient("secret-key")
    client.extract = lambda body, timeout: response
    _install(monkeypatch, "tools.youdotcom_extract", client)
    urls = ["https://example.com/one", "https://example.com/two"]
    messages = _messages(YouComExtractTool, {"urls": "\n".join(urls)})
    assert messages[0].type.value == "json"
    assert [item["url"] for item in _json(messages[0])["results"]] == urls
    assert all(url in _text(messages[1]) for url in urls)
    assert "did not include markdown or html" in _text(messages[1])


def test_search_text_includes_knowledge_provider_attribution(monkeypatch):
    client = RecordingClient("secret-key")
    client.search_payload["results"]["knowledge"] = [{
        "type": "answer", "title": "Company facts", "description": "Revenue data",
        "attribution": "Licensed Data Provider", "as_of": "2026-11-20",
    }]
    _install(monkeypatch, "tools.youdotcom_search", client)
    messages = _messages(YouComSearchTool, {"query": "Company", "knowledge": "core"})
    assert _json(messages[0]) == client.search_payload
    assert "Attribution: Licensed Data Provider" in _text(messages[1])
    assert "Revenue data" in _text(messages[1])


def test_frontier_can_resume_after_a_previous_tool_call_reached_its_wait_limit(monkeypatch):
    clock = {"now": 0.0}

    class Client:
        posts = 0
        gets = 0

        def research(self, body, timeout):
            self.posts += 1
            return {"task_id": "paid-task", "status": "queued"}

        def research_task(self, task_id, timeout):
            assert task_id == "paid-task"
            self.gets += 1
            if self.gets == 1:
                clock["now"] += timeout
                return {"status": "running"}
            return {"status": "completed", "result": {"output": {"content": "Finished"}}}

    def run_with_clock(client, body, max_wait_seconds, **kwargs):
        return run_research(
            client, body, max_wait_seconds, monotonic=lambda: clock["now"], **kwargs,
        )

    client = Client()
    _install(monkeypatch, "tools.youdotcom_research", client)
    monkeypatch.setattr("tools.youdotcom_research.run_research", run_with_clock)
    pending = _messages(YouComResearchTool, {
        "input": "Long question", "research_effort": "frontier", "max_wait_seconds": 15.0,
    })
    task = _json(pending[0])
    assert task["incomplete"] is True
    assert "without submitting a new paid task" in _text(pending[1])
    resumed = _messages(YouComResearchTool, {"task_id": task["task_id"]})
    assert _json(resumed[0])["output"]["content"] == "Finished"
    assert client.posts == 1
    assert client.gets == 2


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_research_terminal_task_errors_also_keep_the_task_id(monkeypatch, status):
    class Client:
        def research_task(self, task_id, timeout):
            return {"status": status, "error": "Task failed"}

    _install(monkeypatch, "tools.youdotcom_research", Client())
    messages = _messages(YouComResearchTool, {"task_id": "terminal-task"})
    assert _json(messages[1])["ok"] is False
    assert _json(messages[1])["task_id"] == "terminal-task"
    assert _json(messages[1])["task"]["status"] == status


def test_extract_api_errors_reach_dify_json_with_metadata_intact(monkeypatch):
    responses = iter([
        (200, {}),
        (502, {"error": {
            "code": "site_blocked", "message": "Site blocked secret-key",
            "retryable": False, "request_id": "req-2",
        }}),
    ])

    def request(session, method, url, **kwargs):
        status, payload = next(responses)
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        response.encoding = "utf-8"
        return response

    monkeypatch.setattr(requests.Session, "request", request)
    messages = _messages(YouComExtractTool, {
        "urls": "https://example.com/empty\nhttps://example.com/blocked",
    })
    payload = _json(messages[0])
    assert payload["results"] == [{"url": "https://example.com/empty"}]
    assert payload["errors"][0]["code"] == "site_blocked"
    assert payload["errors"][0]["retryable"] is False
    assert payload["errors"][0]["request_id"] == "req-2"
    assert "secret-key" not in json.dumps(payload)
    assert "secret-key" not in _text(messages[1])
