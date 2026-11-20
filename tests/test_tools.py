from tools.common import YouComError
from tools.youcom_answer import YouComAnswerTool
from tools.youcom_extract import YouComExtractTool
from tools.youcom_finance_research import YouComFinanceResearchTool
from tools.youcom_research import YouComResearchTool, run_research
from tools.youcom_search import YouComSearchTool
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
    creds = {"youcom_api_key": "secret-key"} if credentials is None else credentials
    return list(tool_cls.from_credentials(creds).invoke(parameters))


def test_search_returns_json_then_text(monkeypatch):
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youcom_search", client)
    messages = _messages(YouComSearchTool, {"query": "headlines", "count": 2})
    assert [message.type.value for message in messages] == ["json", "text"]
    assert _json(messages[0])["results"]["web"][0]["url"].endswith("/story")
    assert "Story" in _text(messages[1])
    assert "news intent" in messages[1].message.text
    assert client.calls[0][0] == "search"
    assert client.calls[0][1]["count"] == 2


def test_extract_continues_after_a_page_error_and_stops_on_401(monkeypatch):
    client = RecordingClient("secret-key")
    _install(monkeypatch, "tools.youcom_extract", client)
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
    _install(monkeypatch, "tools.youcom_answer", client)
    messages = _messages(YouComAnswerTool, {"query": "What shipped?"})
    assert _json(messages[0])["answer"].startswith("Cited")
    assert "https://example.com" in _text(messages[1])
    assert client.calls[0][0] == "answer"

    _install(monkeypatch, "tools.youcom_finance_research", client)
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
        "tools.youcom_search.YouComClient",
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

    monkeypatch.setattr("tools.youcom_research.YouComClient", Client)
    messages = _messages(YouComResearchTool, {"input": "Summarize the category"})
    assert seen["body"]["research_effort"] == "standard"
    assert seen["timeout"] == 45.0
    assert messages[0].type.value == "json"
    assert "Standard note" in _text(messages[1])


def test_search_formatter_mentions_empty_results():
    text = format_search({"results": {"web": []}})
    assert "No web or knowledge results" in text
