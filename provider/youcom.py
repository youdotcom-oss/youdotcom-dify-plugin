from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.common import YouComClient, YouComError


class YouComProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = str((credentials or {}).get("youcom_api_key") or "").strip()
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "You.com API key is required. Get one at https://you.com/platform."
            )
        try:
            # A one-result snippet search is the cheapest authenticated call.
            YouComClient(api_key).search({"query": "You.com", "count": 1}, timeout=20)
        except YouComError as exc:
            raise ToolProviderCredentialValidationError(str(exc)) from exc
