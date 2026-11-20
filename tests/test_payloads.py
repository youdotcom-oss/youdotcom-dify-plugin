import json

import pytest

from tools.common import YouComError
from tools.payloads import (
    build_answer_body,
    build_extract_calls,
    build_finance_body,
    build_research_body,
    build_search_body,
)


def test_search_body_covers_documented_controls():
    body = build_search_body(
        {
            "query": "site:sec.gov Rivian 10-K",
            "count": "5",
            "freshness": "week",
            "country": "us",
            "language": "en",
            "offset": "1",
            "safesearch": "strict",
            "include_domains": "sec.gov, www.investor.example.com",
            "strict_operators": "true",
            "knowledge": "core",
            "extraction_mode": "highlights",
            "highlights_total_max_tokens": "2048",
        }
    )
    assert body["query"].startswith("site:sec.gov")
    assert body["count"] == 5
    assert body["freshness"] == "week"
    assert body["country"] == "US"
    assert body["language"] == "EN"
    assert body["offset"] == 1
    assert body["safesearch"] == "strict"
    assert body["include_domains"] == ["sec.gov", "www.investor.example.com"]
    assert body["strict_operators"] is True
    assert body["knowledge"] == "core"
    assert body["extraction"] == {
        "extraction_mode": "highlights",
        "highlights": {"total_max_tokens": 2048},
    }
    assert "crawl_timeout" not in body
    assert "extraction_source" not in body["extraction"]


def test_freshness_range_overrides_preset_and_full_page_shape():
    body = build_search_body(
        {
            "query": "LangGraph release",
            "freshness": "year",
            "freshness_range": "2025-01-01to2025-03-31",
            "extraction_mode": "full_page",
            "extraction_formats": "both",
            "extraction_source": "fetch",
            "crawl_timeout": 45,
        }
    )
    assert body["freshness"] == "2025-01-01to2025-03-31"
    assert body["crawl_timeout"] == 45
    assert body["extraction"]["extraction_source"] == "fetch"
    assert body["extraction"]["full_page"]["extraction_formats"] == ["markdown", "html"]


def test_search_rejects_conflicting_domains_and_highlight_limits():
    with pytest.raises(YouComError, match="cannot be used together"):
        build_search_body(
            {"query": "test", "include_domains": "a.com", "exclude_domains": "b.com"}
        )
    with pytest.raises(YouComError, match="boost_domains"):
        build_search_body(
            {"query": "test", "include_domains": "a.com", "boost_domains": "a.com"}
        )
    with pytest.raises(YouComError, match="50"):
        build_search_body({"query": "test", "count": 51, "extraction_mode": "highlights"})
    with pytest.raises(YouComError, match="crawl_timeout"):
        build_search_body({"query": "test", "extraction_mode": "highlights", "crawl_timeout": 10})


def test_extract_calls_current_endpoint_once_per_url():
    calls = build_extract_calls(
        {
            "urls": "https://example.com/a, https://example.com/a\nhttps://example.com/b.pdf",
            "formats": "html",
            "extraction_source": "cache",
            "timeout": "20",
            "parse_effort": "lite",
        }
    )
    assert [url for url, _, _ in calls] == ["https://example.com/a", "https://example.com/b.pdf"]
    _, body, timeout = calls[0]
    assert body == {
        "url": "https://example.com/a",
        "extraction_source": "cache",
        "timeout": 20,
        "parse_effort": "lite",
        "full_page": {"extraction_formats": ["html"]},
    }
    assert timeout == 30
    with pytest.raises(YouComError, match="absolute http"):
        build_extract_calls({"urls": "file:///etc/passwd"})


def test_answer_uses_its_own_language_list():
    body = build_answer_body({"query": "What changed?", "language": "DE", "safesearch": "off"})
    assert body["language"] == "DE"
    assert body["safesearch"] == "off"
    with pytest.raises(YouComError, match="language"):
        build_answer_body({"query": "日本語", "language": "JA"})


def test_research_and_finance_bodies():
    research = build_research_body(
        {
            "input": "Compare two vendors",
            "research_effort": "deep",
            "exclude_domains": "reddit.com",
            "country": "GB",
            "output_schema": json.dumps(
                {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                    "additionalProperties": False,
                }
            ),
        }
    )
    assert research["research_effort"] == "deep"
    assert research["source_control"]["country"] == "GB"
    assert research["source_control"]["exclude_domains"] == ["reddit.com"]
    assert research["output_schema"]["required"] == ["summary"]

    with pytest.raises(YouComError, match="lite"):
        build_research_body({"input": "short", "research_effort": "lite", "output_schema": "{}"})

    finance = build_finance_body({"input": "Latest quarter revenue", "research_effort": "exhaustive"})
    assert finance == {"input": "Latest quarter revenue", "research_effort": "exhaustive"}
    with pytest.raises(YouComError, match="deep or exhaustive"):
        build_finance_body({"input": "revenue", "research_effort": "lite"})
