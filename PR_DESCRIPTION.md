# Plugin Submission

## Plugin information

- **Author**: youdotcom
- **Plugin name**: youdotcom
- **Version**: 0.1.0
- **Source repository**: https://github.com/youdotcom-oss/youdotcom-dify-plugin
- **Contact**: api@you.com

## Submission type

- [x] New plugin
- [ ] Version update

## What changed

This is the first You.com tool plugin for Dify. It gives a workspace five tools, all authenticated with the user's You.com API key (`X-API-Key`):

- Search calls `POST https://ydc-index.io/v1/search`. Web and news results come back in one `results.web` list. Count, freshness, country, language, SafeSearch, domain filters, knowledge, highlights, and full-page content are exposed.
- Extract calls `POST https://ydc-index.io/v1/extract` once per URL and returns Markdown or HTML. The current Extract API takes one URL per request, so a batch is several calls, capped at five.
- Answer calls `POST https://api.you.com/v1/answer` and returns a cited answer. This is the Answer API. It is not Research, and the request has no model field.
- Research calls `POST https://api.you.com/v1/research`. Effort can be lite, standard, deep, exhaustive, or frontier. Frontier is sent with `background: true` and polled with `GET /v1/research/{task_id}` until the wait limit.
- Finance Research calls `POST https://api.you.com/v1/finance_research` with effort `deep` or `exhaustive`.

Saving the credential runs a one-result search so a bad key fails immediately. Each tool returns a text message and a JSON message. 401, 402, 429 (including a spending cap), and timeouts are returned as errors. A 429 is retried once only when `Retry-After` is two seconds or less.

Please add the file as `youdotcom/youdotcom/youdotcom-0.1.0.difypkg`.

## Risk level

- [ ] Low risk
- [ ] Medium risk
- [x] High risk

Extract asks You.com to fetch URLs the user supplies, and Finance Research sends financial questions to You.com. The plugin does not run commands, SQL, or a browser, and it does not read the local filesystem.

## Required checks

- [x] I have read and followed the [Marketplace submission requirements](https://github.com/langgenius/dify-plugins/blob/main/docs/plugin-submission-requirements.md).
- [x] I have read and comply with the [Plugin Development Guidelines](https://docs.dify.ai/en/develop-plugin/publishing/standards/contributor-covenant-code-of-conduct).
- [x] I tested this plugin on Dify Community Edition and Dify Cloud, or documented any limitation below.
- [x] The package contains only files needed at runtime.
- [x] The package does not contain secrets, local credentials, `.env` files, `.git` directories, virtual environments, caches, logs, or IDE files.
- [x] The package does not contain executables or bundled binaries, or I explained why they are required below.
- [x] The plugin README includes setup steps, usage instructions, required APIs or credentials, connection requirements, and the source repository link.
- [x] The plugin includes `PRIVACY.md` or a hosted privacy policy, and `manifest.yaml` references it.
- [x] All user-facing text is primarily in English, with any localized README files following the [i18n guidance](https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/multilingual-readme).

## Security and privacy notes

Extract sends user-supplied `http` and `https` URLs to You.com, which fetches the pages. Other URL schemes are rejected. That is the input constraint: at most five absolute http(s) URLs per call. Finance Research sends the user's financial question to You.com and does not move money. The security boundary is the two documented hosts. The API key is sent only as `X-API-Key` to `ydc-index.io` and `api.you.com`. The plugin does not follow environment proxy variables, does not log the key, and strips the key from error text if it appears. There is no shell, SQL, filesystem, or browser access.

We have not installed this build on Dify Cloud or Dify Community Edition yet. Validation so far is the unit suite, a package built with the plugin CLI 0.6.15, and the governance scripts against the layout `youdotcom/youdotcom/youdotcom-0.1.0.difypkg`.

## Local validation

```text
pytest -q
21 passed, 5 skipped, 2 warnings in 0.44s
```

The five skipped tests are live smoke calls. They run only when `YDC_API_KEY` is set, and they do not print the key. That variable was not set here.

```text
dify version
v0.6.15

dify plugin package . -o youdotcom-0.1.0.difypkg
```

The archive has 26 files: manifest, README, PRIVACY.md, requirements, provider, tools, and the two icons. It does not contain tests, examples, `.env`, or `PR_DESCRIPTION.md`.

Governance scripts from `.github/scripts/governance` on `main`, pointed at `youdotcom/youdotcom/youdotcom-0.1.0.difypkg`:

```text
check_packaging_rules.py  exit 0  (0 blocking findings)
check_manifest_tags.py    exit 0  (tags: search, finance)
check_near_duplicates.py  exit 0
```

The near-duplicate run only had this package in the tree, so it did not compare against every package already in the marketplace repository. `youdotcom/` is not an existing author directory there. `GET https://marketplace.dify.ai/api/v1/plugins/youdotcom/youdotcom/0.1.0` returned `plugin version not found`.

I also ran the marketplace toolkit validators (PR body, README, manifest, package contents, secrets, binaries, dependencies, access domains, sensitive capabilities, financial-activity signals, and Python safety warnings) against this package. They reported no errors.

A copy of the same file placed at `youdotcom/youdotcom-0.1.0.difypkg` fails the packaging rule, which is why the path above has its own plugin directory.

## Reviewer notes

- Search uses `POST /v1/search`. News articles are part of `results.web` when the query is about news. There is no separate news endpoint in the current docs.
- `POST /v1/contents` is deprecated in the current spec. Extract does not call it.
- Answer has no research-effort or model parameter. Research is the separate endpoint, and `standard` is its default effort.
- Frontier research can run far longer than a tool call. The tool submits it in background mode and stops polling at `max_wait_seconds` (default 180, maximum 300), returning the task id if it is still running.
- The source repository is https://github.com/youdotcom-oss/youdotcom-dify-plugin.
- Related marketplace discussion: https://github.com/langgenius/dify-plugins/issues/3869
- Finance Research accepts `deep` and `exhaustive` only, and it does not accept source controls.
