# You.com for Dify

A Dify tool plugin for the You.com Web Search, Extract, Answer, Research, and Finance Research APIs.

Get an API key at [you.com/platform](https://you.com/platform). Every request sends that key in the `X-API-Key` header.

## Tools

| Tool | Method and URL | What you get |
| --- | --- | --- |
| You.com Search | `POST https://ydc-index.io/v1/search` | Web results, with news articles in the same `results.web` list when the query has news intent. Snippets by default. Highlights or a full page on request. |
| You.com Extract | `POST https://ydc-index.io/v1/extract` | Markdown or HTML for one or more pages or PDFs. One request per URL. |
| You.com Answer | `POST https://api.you.com/v1/answer` | One grounded answer with inline citations. |
| You.com Research | `POST https://api.you.com/v1/research` | A cited research answer. `frontier` is submitted with `background: true` and polled with `GET /v1/research/{task_id}`. |
| You.com Finance Research | `POST https://api.you.com/v1/finance_research` | A cited answer from the finance index. Effort is `deep` or `exhaustive`. |

Answer is the Answer API. It is not the Research API, and the request has no model name and no research-effort field. A fast cited answer is Answer. A multi-step cited report is Research, where `lite` is the fastest effort and `standard` is the default.

News does not have its own endpoint. The Web Search API puts news articles in `results.web` beside other web results when the query is about news. Use `freshness`, `country`, and `language` to steer that list. The older `GET /v1/search` path is still up, and this plugin calls `POST /v1/search`, which is the path that accepts highlights, full-page content, and knowledge.

`POST /v1/contents` is marked deprecated in the current OpenAPI spec and accepts a batch of URLs. Extract in this plugin calls `POST /v1/extract` once per URL (maximum 5) so it stays on the current endpoint. `parse_effort` applies to PDFs. Web pages ignore it.

Finance Research does not accept `source_control`. Use Research when you need domain, freshness, or country limits. Finance effort values are only `deep` (default, under 120 seconds) and `exhaustive` (under 300 seconds).

Research effort:

| Effort | What the docs say | How this plugin calls it |
| --- | --- | --- |
| `lite` | Under about 10 seconds | Synchronous. No `output_schema`. |
| `standard` | Default. About 10–30 seconds | Synchronous. |
| `deep` | Under 120 seconds | Synchronous. |
| `exhaustive` | Under 300 seconds | Synchronous. The plugin read timeout is 320 seconds. |
| `frontier` | Requires `background: true`. Can run for a long time | Background task, then poll. `max_wait_seconds` defaults to 180 and caps at 300. If the task is still running, the tool returns the task id instead of waiting for hours. |

## Install

From this directory, with the Dify plugin CLI:

```bash
dify plugin package . -o youcom-0.1.0.difypkg
```

`youcom-0.1.0.difypkg` in this directory is that package. For a marketplace submission, put it at `youdotcom/youcom/youcom-0.1.0.difypkg` in the community plugins repository. A package file sitting directly under the author folder fails the packaging check.

In Dify, open Plugins, install the `.difypkg`, and paste the API key. Saving the credential runs `POST /v1/search` with `count: 1` so a bad key fails before a workflow uses it.

For remote debugging, copy `.env.example` to `.env` and fill in the host and key from the plugin debug card. Do not commit `.env`.

```bash
pip install -r requirements.txt
python -m main
```

## Use in an agent or a workflow

Each tool returns a JSON message and a text message.

- Agents should read the text. It is a short rendering of titles, URLs, snippets or page text, and citations. Full-page bodies in that text are clipped. The JSON message keeps the API payload.
- Workflows should read the JSON output when a later node needs fields. On failure the text is the error, and the JSON is `{"ok": false, "error": "...", "status_code": ...}`.

`include_domains` cannot be combined with `exclude_domains`. `boost_domains` cannot be combined with `include_domains`. A custom freshness window uses `YYYY-MM-DDtoYYYY-MM-DD` and overrides the day/week/month/year preset.

401 means the key was rejected. 402 means the account needs credits at [you.com/platform](https://you.com/platform). 429 is either a rate limit or a spending cap (`spend_cap_exceeded`). A spending cap will not succeed on retry. Timeouts return an error instead of hanging. The plugin retries a 429 once only when `Retry-After` is 2 seconds or less.

The plugin calls You.com directly. It does not read `HTTP_PROXY` or `HTTPS_PROXY`.

## Examples

`examples/` has two workflow files you can import after the plugin is installed:

- `competitor_review_intelligence.yml` searches recent reviews, researches the competitor, and answers a cited question.
- `supplier_vendor_research.yml` searches a vendor, extracts the vendor site, and runs finance research when the vendor is a public company.

If a tool node shows as unavailable after import, reselect You.com on that node. The provider id in the file is `youdotcom/youcom/youcom`.

## Develop

Python 3.12.

```bash
pip install -r requirements.txt pytest
pytest -q
```

`tests/test_live.py` calls each API once when `YDC_API_KEY` is set. The tests do not print the key. Without the variable, those five tests are skipped.

## Privacy

Queries, URLs, and research prompts are sent to You.com to run the tool you selected. See [PRIVACY.md](PRIVACY.md).

## Security boundary

Extract fetches URLs you supply, through You.com, and Finance Research handles financial questions. The plugin does not run shell commands, SQL, or browser automation, and it does not read the local filesystem. URL schemes other than `http` and `https` are rejected. Errors are scrubbed of the API key.

## Source

The plugin source is published at <https://github.com/youdotcom-oss/youdotcom-dify-plugin>.

## Maintainer

You.com. Questions about the APIs: [api@you.com](mailto:api@you.com). Documentation: [you.com/docs](https://you.com/docs).
