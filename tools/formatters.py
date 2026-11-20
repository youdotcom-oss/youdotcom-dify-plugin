"""Turn API payloads into the text message agents read. JSON messages keep the full payload."""

from __future__ import annotations

import json
from typing import Any

TEXT_PAGE_LIMIT = 4000


def _clip(text: str, limit: int = TEXT_PAGE_LIMIT) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n\n[Text truncated. The JSON output has the full content.]"


def format_search(payload: dict[str, Any]) -> str:
    results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
    web = results.get("web") if isinstance(results.get("web"), list) else []
    knowledge = results.get("knowledge") if isinstance(results.get("knowledge"), list) else []
    lines: list[str] = []
    if not web and not knowledge:
        lines.append("No web or knowledge results were returned.")
    for index, item in enumerate(web, start=1):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        lines.append(f"# Result {index}: [{title}]({url})")
        if url:
            lines.append(f"**URL:** {url}")
        if item.get("page_age"):
            lines.append(f"**Page age:** {item['page_age']}")
        if item.get("description"):
            lines.append(f"**Description:** {item['description']}")
        snippets = item.get("snippets") if isinstance(item.get("snippets"), list) else []
        if snippets:
            lines.append("**Snippets:**")
            lines.extend(f"- {snippet}" for snippet in snippets if snippet)
        contents = item.get("contents") if isinstance(item.get("contents"), dict) else {}
        highlights = contents.get("highlights") if isinstance(contents.get("highlights"), list) else []
        if highlights:
            lines.append("**Highlights:**")
            lines.extend(f"- {highlight}" for highlight in highlights if highlight)
        if contents.get("markdown"):
            lines.append("**Markdown:**")
            lines.append(_clip(str(contents["markdown"])))
        if contents.get("html"):
            lines.append("**HTML:**")
            lines.append(_clip(str(contents["html"])))
        lines.append("---")
    if knowledge:
        lines.append("# Knowledge")
        for item in knowledge:
            if not isinstance(item, dict):
                continue
            lines.append(f"**{item.get('title') or 'Knowledge result'}**")
            if item.get("description"):
                lines.append(str(item["description"]))
            if item.get("as_of"):
                lines.append(f"As of {item['as_of']}")
            if item.get("attribution"):
                lines.append(f"Attribution: {item['attribution']}")
    if payload.get("metadata", {}).get("query") if isinstance(payload.get("metadata"), dict) else False:
        lines.append(f"Query: {payload['metadata']['query']}")
    lines.append(
        "News articles are included in these web results when the query has news intent. "
        "There is no separate news array."
    )
    return "\n\n".join(lines).strip()


def format_extract(payload: dict[str, Any]) -> str:
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    lines: list[str] = []
    if not results and not errors:
        lines.append("No page content was returned.")
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "Untitled page"
        url = item.get("url") or ""
        lines.append(f"# Page {index}: [{title}]({url})")
        if item.get("extraction_source"):
            lines.append(f"**Source:** {item['extraction_source']}")
        contents = item.get("contents") if isinstance(item.get("contents"), dict) else {}
        full_page = contents.get("full_page") if isinstance(contents.get("full_page"), dict) else {}
        if full_page.get("markdown"):
            lines.append(_clip(str(full_page["markdown"])))
        if full_page.get("html"):
            lines.append("**HTML:**")
            lines.append(_clip(str(full_page["html"])))
        if not full_page.get("markdown") and not full_page.get("html"):
            lines.append("The page response did not include markdown or html.")
        lines.append("---")
    for error in errors:
        if isinstance(error, dict):
            lines.append(f"Failed to extract {error.get('url')}: {error.get('error')}")
    return "\n\n".join(lines).strip()


def format_answer(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    answer = payload.get("answer")
    if answer:
        lines.append(str(answer).strip())
    citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
    if citations:
        lines.append("## Citations")
        for index, citation in enumerate(citations, start=1):
            if not isinstance(citation, dict):
                continue
            source = citation.get("source") or ""
            lines.append(f"{index}. {source}")
            excerpts = citation.get("excerpts") if isinstance(citation.get("excerpts"), list) else []
            for excerpt in excerpts[:2]:
                if excerpt:
                    lines.append(f"   - {_clip(str(excerpt), 500)}")
    return "\n\n".join(lines).strip() or "The Answer API did not return an answer."


def format_research(payload: dict[str, Any]) -> str:
    if payload.get("incomplete"):
        status = payload.get("status") or "running"
        task_id = payload.get("task_id") or ""
        return (
            f"Frontier research is still {status}. Task id: {task_id}. "
            "The Research API can take much longer than one tool call at this effort. "
            "Call You.com Research again with this task_id to resume polling without submitting "
            "a new paid task. max_wait_seconds controls each polling window."
        )
    output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
    content = output.get("content")
    lines: list[str] = []
    if isinstance(content, str):
        lines.append(content.strip())
    elif content is not None:
        lines.append(json.dumps(content, indent=2, ensure_ascii=False))
    else:
        lines.append("The research response did not include output.content.")
    sources = output.get("sources") if isinstance(output.get("sources"), list) else []
    if sources:
        lines.append("## Sources")
        for index, source in enumerate(sources, start=1):
            if not isinstance(source, dict):
                continue
            title = source.get("title") or source.get("url") or "Source"
            url = source.get("url") or ""
            lines.append(f"{index}. [{title}]({url})" if url else f"{index}. {title}")
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    if warnings:
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n\n".join(lines).strip()
