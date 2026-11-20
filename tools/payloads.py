"""Build request bodies from tool parameters. Field names match the live OpenAPI spec."""

from __future__ import annotations

from typing import Any

from .common import (
    ANSWER_LANGUAGES,
    FINANCE_EFFORTS,
    MAX_INPUT_CHARS,
    RESEARCH_EFFORTS,
    SEARCH_LANGUAGES,
    YouComError,
    apply_domain_filters,
    as_bool,
    as_int,
    country_value,
    freshness_value,
    language_value,
    optional_int,
    parse_output_schema,
    parse_urls,
    require_text,
    unset,
)


def build_search_body(parameters: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"query": require_text(parameters.get("query"), "query")}
    count = optional_int(parameters.get("count"), "count", 1, 100)
    if count is None:
        count = 10

    mode = str(parameters.get("extraction_mode") or "").strip().lower()
    if unset(mode) or mode in {"none", "snippets"}:
        mode = ""
    elif mode not in {"highlights", "full_page"}:
        raise YouComError("extraction_mode must be none, highlights, or full_page.")
    if mode == "highlights" and count > 50:
        raise YouComError("count must be from 1 to 50 when extraction_mode is highlights.")
    body["count"] = count

    fresh = freshness_value(parameters)
    if fresh:
        body["freshness"] = fresh
    country = country_value(parameters)
    if country:
        body["country"] = country
    language = language_value(parameters, SEARCH_LANGUAGES)
    if language:
        body["language"] = language
    offset = optional_int(parameters.get("offset"), "offset", 0, 9)
    if offset:
        body["offset"] = offset
    safesearch = str(parameters.get("safesearch") or "").strip().lower()
    if not unset(safesearch):
        if safesearch not in {"off", "moderate", "strict"}:
            raise YouComError("safesearch must be off, moderate, or strict.")
        body["safesearch"] = safesearch
    apply_domain_filters(body, parameters, include_limit=500, exclude_limit=5000)
    if as_bool(parameters.get("strict_operators")):
        body["strict_operators"] = True
    if str(parameters.get("knowledge") or "").strip().lower() == "core":
        body["knowledge"] = "core"

    source = str(parameters.get("extraction_source") or "").strip().lower()
    if unset(source):
        source = ""
    elif source not in {"blend", "cache", "fetch"}:
        raise YouComError("extraction_source must be blend, cache, or fetch.")
    formats = _formats(parameters.get("extraction_formats"))
    tokens = optional_int(
        parameters.get("highlights_total_max_tokens"),
        "highlights_total_max_tokens",
        1024,
        8192,
    )
    crawl_timeout = optional_int(parameters.get("crawl_timeout"), "crawl_timeout", 1, 60)

    if mode == "highlights":
        if source:
            raise YouComError("extraction_source is only valid with extraction_mode full_page.")
        if crawl_timeout is not None:
            raise YouComError("crawl_timeout is only valid with extraction_mode full_page.")
        extraction: dict[str, Any] = {"extraction_mode": "highlights"}
        if tokens is not None:
            extraction["highlights"] = {"total_max_tokens": tokens}
        body["extraction"] = extraction
    elif mode == "full_page":
        extraction = {
            "extraction_mode": "full_page",
            "extraction_source": source or "blend",
            "full_page": {"extraction_formats": formats or ["markdown"]},
        }
        body["extraction"] = extraction
        if crawl_timeout is not None:
            body["crawl_timeout"] = crawl_timeout
    else:
        if source:
            raise YouComError("extraction_source requires extraction_mode full_page.")
        if tokens is not None:
            raise YouComError("highlights_total_max_tokens requires extraction_mode highlights.")
        if crawl_timeout is not None:
            raise YouComError("crawl_timeout requires extraction_mode full_page.")
    return body


def search_timeout(body: dict[str, Any]) -> float:
    crawl = body.get("crawl_timeout")
    if isinstance(crawl, int):
        return float(crawl + 15)
    return 30.0


def build_extract_calls(parameters: dict[str, Any]) -> list[tuple[str, dict[str, Any], float]]:
    urls = parse_urls(parameters.get("urls"))
    timeout = optional_int(parameters.get("timeout"), "timeout", 2, 100)
    if timeout is None:
        timeout = 30
    if len(urls) * (timeout + 10) > 330:
        raise YouComError(
            "That combination of URLs and timeout can exceed the tool time limit. "
            "Lower timeout or send fewer URLs."
        )
    source = str(parameters.get("extraction_source") or "").strip().lower()
    if unset(source):
        source = "blend"
    if source not in {"blend", "cache", "fetch"}:
        raise YouComError("extraction_source must be blend, cache, or fetch.")
    effort = str(parameters.get("parse_effort") or "").strip().lower()
    if unset(effort):
        effort = "standard"
    if effort not in {"lite", "standard"}:
        raise YouComError("parse_effort must be lite or standard.")
    formats = _formats(parameters.get("formats")) or ["markdown"]
    calls: list[tuple[str, dict[str, Any], float]] = []
    for url in urls:
        body = {
            "url": url,
            "extraction_source": source,
            "timeout": timeout,
            "parse_effort": effort,
            "full_page": {"extraction_formats": formats},
        }
        calls.append((url, body, float(timeout + 10)))
    return calls


def build_answer_body(parameters: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"query": require_text(parameters.get("query"), "query")}
    fresh = freshness_value(parameters)
    if fresh:
        body["freshness"] = fresh
    country = country_value(parameters)
    if country:
        body["country"] = country
    language = language_value(parameters, ANSWER_LANGUAGES)
    if language:
        body["language"] = language
    safesearch = str(parameters.get("safesearch") or "").strip().lower()
    if not unset(safesearch):
        if safesearch not in {"off", "moderate", "strict"}:
            raise YouComError("safesearch must be off, moderate, or strict.")
        body["safesearch"] = safesearch
    # Answer caps both domain lists at 500.
    apply_domain_filters(body, parameters, include_limit=500, exclude_limit=500)
    return body


def build_research_body(parameters: dict[str, Any]) -> dict[str, Any]:
    effort = str(parameters.get("research_effort") or "").strip().lower()
    if unset(effort):
        effort = "standard"
    if effort not in RESEARCH_EFFORTS:
        raise YouComError(
            "research_effort must be lite, standard, deep, exhaustive, or frontier."
        )
    body: dict[str, Any] = {
        "input": require_text(parameters.get("input"), "input", MAX_INPUT_CHARS),
        "research_effort": effort,
    }
    schema = parse_output_schema(parameters.get("output_schema"))
    if schema is not None:
        if effort == "lite":
            raise YouComError("output_schema is not accepted when research_effort is lite.")
        body["output_schema"] = schema
    source_control: dict[str, Any] = {}
    apply_domain_filters(source_control, parameters, include_limit=500, exclude_limit=500)
    fresh = freshness_value(parameters)
    if fresh:
        source_control["freshness"] = fresh
    country = country_value(parameters)
    if country:
        source_control["country"] = country
    if source_control:
        body["source_control"] = source_control
    return body


def research_read_timeout(effort: str) -> float:
    return {"lite": 30.0, "standard": 45.0, "deep": 150.0, "exhaustive": 320.0}.get(effort, 60.0)


def frontier_wait_seconds(parameters: dict[str, Any]) -> int:
    raw = parameters.get("max_wait_seconds")
    if unset(raw):
        return 180
    return as_int(raw, "max_wait_seconds", 15, 300)


def build_finance_body(parameters: dict[str, Any]) -> dict[str, Any]:
    effort = str(parameters.get("research_effort") or "").strip().lower()
    if unset(effort):
        effort = "deep"
    if effort not in FINANCE_EFFORTS:
        raise YouComError("research_effort must be deep or exhaustive for finance research.")
    body: dict[str, Any] = {
        "input": require_text(parameters.get("input"), "input", MAX_INPUT_CHARS),
        "research_effort": effort,
    }
    schema = parse_output_schema(parameters.get("output_schema"))
    if schema is not None:
        body["output_schema"] = schema
    return body


def finance_read_timeout(effort: str) -> float:
    return 150.0 if effort == "deep" else 320.0


def _formats(value: Any) -> list[str]:
    raw = str(value or "").strip().lower()
    if unset(raw):
        return []
    if raw == "both":
        return ["markdown", "html"]
    if raw in {"markdown", "html"}:
        return [raw]
    raise YouComError("formats must be markdown, html, or both.")
