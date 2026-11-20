"""Live smoke calls. Skipped unless YDC_API_KEY is set. The key is never printed."""

import os

import pytest

from tools.common import YouComClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("YDC_API_KEY"),
    reason="YDC_API_KEY is not set",
)


@pytest.fixture(scope="module")
def client():
    return YouComClient(os.environ["YDC_API_KEY"])


def test_live_search(client):
    payload = client.search({"query": "You.com API documentation", "count": 1}, timeout=30)
    assert isinstance(payload.get("results"), dict)


def test_live_extract(client):
    payload = client.extract(
        {
            "url": "https://example.com",
            "timeout": 20,
            "full_page": {"extraction_formats": ["markdown"]},
        },
        timeout=30,
    )
    assert payload.get("url")


def test_live_answer(client):
    payload = client.answer({"query": "What is the You.com Web Search API?"}, timeout=60)
    assert payload.get("answer")


def test_live_research(client):
    payload = client.research(
        {"input": "What is the You.com Web Search API used for?", "research_effort": "lite"},
        timeout=40,
    )
    assert payload.get("output", {}).get("content")


def test_live_finance_research(client):
    payload = client.finance_research(
        {
            "input": "What was Apple's most recently reported total net sales figure?",
            "research_effort": "deep",
        },
        timeout=150,
    )
    assert payload.get("output", {}).get("content")
