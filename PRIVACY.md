# Privacy Policy

This plugin sends a request to You.com only when you run one of its tools.

## What is sent

- Search sends the query and the filters you set, such as count, freshness, country, language, SafeSearch, and domain lists.
- Extract sends the URLs you supply and the format, source, timeout, and PDF parse options you set. You.com fetches those pages.
- Answer sends the question and the same kind of search filters the Answer API accepts.
- Research sends the question, the effort level, optional source controls, and an optional JSON schema.
- Finance Research sends the financial question, the effort level, and an optional JSON schema.

The API key you enter in Dify is sent only as the `X-API-Key` header to `https://ydc-index.io` (Search and Extract) or `https://api.you.com` (Answer, Research, and Finance Research). The plugin does not write the key to logs, and error text returned to the workflow has the key removed if it appears.

## What this plugin stores

The plugin does not add its own database, file store, or analytics. Dify keeps the credential in your workspace. You.com processes the request under the terms and privacy policy of the You.com API account that owns the key.

## Proxy settings

The plugin does not offer a proxy field, and it does not inherit `HTTP_PROXY` or `HTTPS_PROXY` from the environment. Calls go directly to the two hosts above.

## Contact

Questions about this plugin's data handling can go to the address on your You.com account, or to api@you.com.
