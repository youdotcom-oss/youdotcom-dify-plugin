"""HTTP client and shared helpers for the You.com Dify tools."""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests

SEARCH_HOST = "https://ydc-index.io"
API_HOST = "https://api.you.com"
KEY_URL = "https://you.com/platform"

COUNTRIES = (
    "AR", "AU", "AT", "BE", "BR", "CA", "CL", "DK", "FI", "FR", "DE", "HK",
    "IN", "ID", "IT", "JP", "KR", "MY", "MX", "NL", "NZ", "NO", "CN", "PL",
    "PT", "PH", "RU", "SA", "ZA", "ES", "SE", "CH", "TW", "TR", "GB", "US",
)
SEARCH_LANGUAGES = (
    "AR", "EU", "BN", "BG", "CA", "ZH-HANS", "ZH-HANT", "HR", "CS", "DA", "NL",
    "EN", "EN-GB", "ET", "FI", "FR", "GL", "DE", "EL", "GU", "HE", "HI", "HU",
    "IS", "IT", "JA", "KN", "KO", "LV", "LT", "MS", "ML", "MR", "NB", "PL",
    "PT-BR", "PT-PT", "PA", "RO", "RU", "SR", "SK", "SL", "ES", "SV", "TA", "TE",
    "TH", "TR", "UK", "VI",
)
# The Answer API accepts a smaller language set than Web Search.
ANSWER_LANGUAGES = tuple(
    code for code in SEARCH_LANGUAGES if code not in {"ZH-HANS", "ZH-HANT", "JA", "PT-BR", "PT-PT"}
)
FRESHNESS_PRESETS = ("day", "week", "month", "year")
SAFESEARCH = ("off", "moderate", "strict")
RESEARCH_EFFORTS = ("lite", "standard", "deep", "exhaustive", "frontier")
FINANCE_EFFORTS = ("deep", "exhaustive")
DATE_RANGE = re.compile(r"^\d{4}-\d{2}-\d{2}to\d{4}-\d{2}-\d{2}$")
MAX_EXTRACT_URLS = 5
MAX_INPUT_CHARS = 40000


class YouComError(Exception):
    """A request that should be shown to the user, with the API key removed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def credential_key(credentials: dict[str, Any] | None) -> str:
    raw = str((credentials or {}).get("youdotcom_api_key") or "").strip()
    if not raw:
        raise YouComError(
            "You.com API key is missing. Add it in the plugin credentials. "
            f"Get a key at {KEY_URL}."
        )
    return raw


def redact(text: str, needle: str) -> str:
    if needle and needle in text:
        return text.replace(needle, "[redacted]")
    return text


def unset(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "none", "not_specified", "null"}:
        return True
    return False


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def as_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise YouComError(f"{field} must be a whole number from {minimum} to {maximum}.")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise YouComError(f"{field} must be a whole number from {minimum} to {maximum}.") from exc
    if number < minimum or number > maximum:
        raise YouComError(f"{field} must be from {minimum} to {maximum}.")
    return number


def optional_int(value: Any, field: str, minimum: int, maximum: int) -> int | None:
    if unset(value):
        return None
    return as_int(value, field, minimum, maximum)


def split_terms(value: Any) -> list[str]:
    if unset(value):
        return []
    if isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        parts = re.split(r"[\s,]+", str(value))
    terms: list[str] = []
    seen: set[str] = set()
    for part in parts:
        term = part.strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def domain_list(value: Any, field: str, limit: int) -> list[str]:
    domains: list[str] = []
    for raw in split_terms(value):
        candidate = raw
        if "://" in candidate:
            parsed = urlparse(candidate)
            candidate = parsed.netloc or parsed.path
        candidate = candidate.split("/")[0].strip().lower().strip(".")
        if not candidate or " " in candidate or "." not in candidate:
            raise YouComError(f"{field} must be domain names, such as example.com.")
        if candidate not in domains:
            domains.append(candidate)
    if len(domains) > limit:
        raise YouComError(f"{field} accepts at most {limit} domains.")
    return domains


def apply_domain_filters(
    body: dict[str, Any],
    parameters: dict[str, Any],
    *,
    include_limit: int,
    exclude_limit: int,
) -> None:
    include = domain_list(parameters.get("include_domains"), "include_domains", include_limit)
    exclude = domain_list(parameters.get("exclude_domains"), "exclude_domains", exclude_limit)
    boost = domain_list(parameters.get("boost_domains"), "boost_domains", 500)
    if include and exclude:
        raise YouComError("include_domains and exclude_domains cannot be used together.")
    if include and boost:
        raise YouComError("boost_domains cannot be combined with include_domains.")
    if include:
        body["include_domains"] = include
    if exclude:
        body["exclude_domains"] = exclude
    if boost:
        body["boost_domains"] = boost


def freshness_value(parameters: dict[str, Any]) -> str | None:
    custom = str(parameters.get("freshness_range") or "").strip()
    preset = str(parameters.get("freshness") or "").strip().lower()
    if custom and not unset(custom):
        if not DATE_RANGE.match(custom):
            raise YouComError(
                "freshness_range must look like 2026-01-01to2026-03-31 "
                "(YYYY-MM-DDtoYYYY-MM-DD, with no spaces)."
            )
        return custom
    if unset(preset):
        return None
    if preset not in FRESHNESS_PRESETS:
        raise YouComError("freshness must be day, week, month, year, or left unset.")
    return preset


def country_value(parameters: dict[str, Any]) -> str | None:
    country = str(parameters.get("country") or "").strip().upper()
    if unset(country):
        return None
    if country not in COUNTRIES:
        raise YouComError(f"country must be one of: {', '.join(COUNTRIES)}.")
    return country


def language_value(parameters: dict[str, Any], allowed: tuple[str, ...], field: str = "language") -> str | None:
    language = str(parameters.get(field) or "").strip().upper()
    if unset(language):
        return None
    if language not in allowed:
        raise YouComError(
            f"{field} must be one of the codes this endpoint accepts: {', '.join(allowed)}."
        )
    return language


def parse_urls(value: Any) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for raw in split_terms(value):
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise YouComError(f"Each URL must be an absolute http or https address. Got: {raw}")
        if raw not in seen:
            seen.add(raw)
            urls.append(raw)
    if not urls:
        raise YouComError("Provide at least one http or https URL.")
    if len(urls) > MAX_EXTRACT_URLS:
        raise YouComError(
            f"Extract accepts up to {MAX_EXTRACT_URLS} URLs per call. "
            "The current Extract API fetches one page per request."
        )
    return urls


def parse_output_schema(value: Any) -> dict[str, Any] | None:
    if unset(value):
        return None
    if isinstance(value, dict):
        schema = value
    else:
        try:
            schema = json.loads(str(value))
        except json.JSONDecodeError as exc:
            raise YouComError("output_schema must be a JSON object.") from exc
    if not isinstance(schema, dict):
        raise YouComError("output_schema must be a JSON object.")
    return schema


def require_text(value: Any, field: str, limit: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        raise YouComError(f"{field} is required.")
    if limit is not None and len(text) > limit:
        raise YouComError(f"{field} must be at most {limit} characters.")
    return text


def _error_detail(payload: Any, text: str) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, list):
            parts: list[str] = []
            for item in detail:
                if isinstance(item, dict) and item.get("msg"):
                    loc = item.get("loc") or []
                    where = ".".join(str(piece) for piece in loc if piece != "body")
                    parts.append(f"{where}: {item['msg']}" if where else str(item["msg"]))
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "; ".join(parts)
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return str(first.get("title") or first.get("detail") or first.get("message") or first)
        for key in ("message", "error", "title"):
            if payload.get(key):
                return str(payload[key])
    snippet = " ".join((text or "").split())
    return snippet[:300] if snippet else "the API did not return a message"


def message_for_status(response: requests.Response, secret: str) -> str:
    text = response.text or ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    detail = redact(_error_detail(payload, text), secret)
    status = response.status_code
    blob = detail.lower()
    if status == 401:
        return (
            "You.com rejected the API key (401). Check the key in the plugin credentials. "
            f"Get a key at {KEY_URL}. {detail}"
        )
    if status == 402:
        return (
            "You.com returned 402. Add credits before retrying. "
            f"{KEY_URL}. {detail}"
        )
    if status == 403:
        return (
            "You.com returned 403 Forbidden. The key may not have access to this API. "
            f"{detail}"
        )
    if status == 429:
        if "spend_cap" in blob or "spending cap" in blob:
            return (
                "You.com returned 429 because this API key reached its spending cap. "
                f"Raise or remove the cap at {KEY_URL}. Retrying will not help. {detail}"
            )
        retry_after = response.headers.get("Retry-After")
        reset = response.headers.get("X-RateLimit-Reset")
        hint = ""
        if retry_after:
            hint = f" Retry-After: {retry_after} seconds."
        elif reset:
            hint = f" The limit window resets at unix time {reset}."
        return f"You.com rate limit reached (429).{hint} {detail}".strip()
    if status == 422:
        return f"You.com rejected the request parameters (422). {detail}"
    if status == 502:
        return f"You.com could not fetch that page (502). {detail}"
    if status == 504:
        return f"You.com timed out while fetching the page (504). Raise timeout, or try again. {detail}"
    return f"You.com returned HTTP {status}. {detail}"


def _retry_after_seconds(response: requests.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class YouComClient:
    """Calls the documented You.com hosts with the X-API-Key header."""

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self.api_key = api_key.strip()
        self.session = session or requests.Session()
        # Ignore HTTP_PROXY so the key is only sent to the You.com hosts below.
        self.session.trust_env = False

    def search(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self._request("POST", SEARCH_HOST, "/v1/search", body, timeout)

    def extract(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self._request("POST", SEARCH_HOST, "/v1/extract", body, timeout)

    def answer(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self._request("POST", API_HOST, "/v1/answer", body, timeout)

    def research(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self._request("POST", API_HOST, "/v1/research", body, timeout)

    def research_task(self, task_id: str, timeout: float) -> dict[str, Any]:
        return self._request("GET", API_HOST, f"/v1/research/{task_id}", None, timeout)

    def finance_research(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self._request("POST", API_HOST, "/v1/finance_research", body, timeout)

    def _request(
        self,
        method: str,
        host: str,
        path: str,
        body: dict[str, Any] | None,
        timeout: float,
        attempt: int = 0,
    ) -> dict[str, Any]:
        url = f"{host}{path}"
        try:
            response = self.session.request(
                method,
                url,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                json=body if method != "GET" else None,
                timeout=(10, timeout),
            )
        except requests.Timeout as exc:
            raise YouComError(
                "The You.com request timed out before a response arrived. "
                "Try again, or lower the timeout, result count, or research effort.",
            ) from exc
        except requests.RequestException as exc:
            raise YouComError("The You.com request failed before a response arrived.") from exc

        if response.status_code == 429 and attempt == 0:
            delay = _retry_after_seconds(response)
            if delay is not None and 0 <= delay <= 2:
                time.sleep(delay)
                return self._request(method, host, path, body, timeout, attempt=1)

        if response.status_code >= 400:
            detail = message_for_status(response, self.api_key)
            raise YouComError(detail, status_code=response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise YouComError(
                "You.com returned a response that was not JSON.",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise YouComError(
                "You.com returned a JSON value that was not an object.",
                status_code=response.status_code,
            )
        return payload
