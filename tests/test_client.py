import json
import time

import gevent
import pytest
import requests

from tools.common import YouComClient, YouComError


class FakeResponse:
    def __init__(self, status, payload=None, text="", headers=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text else (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.trust_env = True

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        if not self.responses:
            raise AssertionError("unexpected request")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_search_sends_api_key_header_and_does_not_trust_env_proxy():
    session = FakeSession([FakeResponse(200, {"results": {"web": []}})])
    client = YouComClient("secret-key", session=session)
    payload = client.search({"query": "ping", "count": 1}, timeout=20)
    assert payload["results"]["web"] == []
    assert session.trust_env is False
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://ydc-index.io/v1/search"
    assert call["headers"]["X-API-Key"] == "secret-key"
    assert call["json"] == {"query": "ping", "count": 1}
    assert call["timeout"] == (10, 20)


def test_401_message_does_not_include_the_key():
    session = FakeSession(
        [FakeResponse(401, {"detail": "Invalid or expired API key secret-key"})]
    )
    client = YouComClient("secret-key", session=session)
    with pytest.raises(YouComError, match="401") as caught:
        client.answer({"query": "hi"}, timeout=10)
    assert "secret-key" not in str(caught.value)
    assert caught.value.status_code == 401
    assert session.calls[0]["url"] == "https://api.you.com/v1/answer"


@pytest.mark.parametrize("payload", [
    {"errors": [{"title": "spend_cap_exceeded"}]},
    {"error": {"code": "spend_cap_exceeded", "message": "Limit reached", "retryable": False}},
    {"detail": "API key spending cap reached"},
])
def test_429_spend_cap_is_not_retried(monkeypatch, payload):
    slept = []
    monkeypatch.setattr("tools.common.time.sleep", slept.append)
    session = FakeSession(
        [FakeResponse(429, payload, headers={"Retry-After": "1"})]
    )
    client = YouComClient("secret-key", session=session)
    with pytest.raises(YouComError, match="spending cap") as caught:
        client.finance_research({"input": "revenue", "research_effort": "deep"}, timeout=10)
    assert caught.value.status_code == 429
    assert len(session.calls) == 1
    assert slept == []
    assert session.calls[0]["url"] == "https://api.you.com/v1/finance_research"


def test_429_retries_once_when_retry_after_is_short(monkeypatch):
    slept = []
    monkeypatch.setattr("tools.common.time.sleep", slept.append)
    session = FakeSession(
        [
            FakeResponse(429, {"errors": [{"title": "Rate limit exceeded"}]}, headers={"Retry-After": "1"}),
            FakeResponse(200, {"answer": "ok", "citations": [], "results": {"web": []}}),
        ]
    )
    client = YouComClient("secret-key", session=session)
    payload = client.answer({"query": "hi"}, timeout=10)
    assert payload["answer"] == "ok"
    assert slept == [1.0]
    assert len(session.calls) == 2


def test_timeout_is_a_youdotcom_error():
    session = FakeSession([requests.Timeout("slow")])
    client = YouComClient("secret-key", session=session)
    with pytest.raises(YouComError, match="timed out") as caught:
        client.extract({"url": "https://example.com"}, timeout=5)
    assert caught.value.status_code is None
    assert session.calls[0]["url"] == "https://ydc-index.io/v1/extract"


def test_research_task_get():
    session = FakeSession([FakeResponse(200, {"id": "task-1", "status": "running", "result": None})])
    client = YouComClient("secret-key", session=session)
    payload = client.research_task("task-1", timeout=30)
    assert payload["status"] == "running"
    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"] == "https://api.you.com/v1/research/task-1"
    assert session.calls[0]["json"] is None


def test_extract_preserves_structured_error_fields_without_leaking_the_key():
    session = FakeSession([FakeResponse(504, {
        "error": {
            "code": "timeout",
            "message": "Could not fetch secret-key",
            "retryable": True,
            "request_id": "req-1",
            "details": {"reason": "secret-key", "fields": ["secret-key"]},
        },
    })])
    client = YouComClient("secret-key", session=session)
    with pytest.raises(YouComError) as caught:
        client.extract({"url": "https://example.com"}, timeout=5)
    error = caught.value.to_dict()
    assert error["code"] == "timeout"
    assert error["retryable"] is True
    assert error["request_id"] == "req-1"
    assert error["details"] == {"reason": "[redacted]", "fields": ["[redacted]"]}
    assert "Could not fetch [redacted]" in error["error"]
    assert "secret-key" not in json.dumps(error)


@pytest.mark.parametrize("rate_limited", [False, True])
def test_research_poll_wall_time_is_bounded_including_retries(rate_limited):
    class SlowSession(FakeSession):
        def request(self, *args, **kwargs):
            if rate_limited:
                return super().request(*args, **kwargs)
            gevent.sleep(0.2)
            return FakeResponse(200, {"status": "running"})

    session = SlowSession([
        FakeResponse(429, {"message": "Rate limit"}, headers={"Retry-After": "1"}),
        FakeResponse(200, {"status": "running"}),
    ])
    started = time.monotonic()
    with pytest.raises(YouComError):
        YouComClient("secret-key", session=session).research_task("task-1", timeout=0.03)
    elapsed = time.monotonic() - started
    assert elapsed < 0.1


def test_research_task_id_is_encoded_as_a_single_path_component():
    session = FakeSession([FakeResponse(200, {"status": "running"})])
    YouComClient("secret-key", session=session).research_task("task/child?key=value#fragment", timeout=1)
    assert session.calls[0]["url"] == (
        "https://api.you.com/v1/research/task%2Fchild%3Fkey%3Dvalue%23fragment"
    )
