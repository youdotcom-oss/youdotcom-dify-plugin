import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.youdotcom import YouComProvider
from tools.common import YouComError


def test_validation_runs_a_one_result_search(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, api_key):
            seen["api_key"] = api_key

        def search(self, body, timeout):
            seen["body"] = body
            seen["timeout"] = timeout
            return {"results": {"web": []}}

    monkeypatch.setattr("provider.youdotcom.YouComClient", Client)
    YouComProvider()._validate_credentials({"youdotcom_api_key": " secret-key "})
    assert seen == {
        "api_key": "secret-key",
        "body": {"query": "You.com", "count": 1},
        "timeout": 20,
    }


def test_validation_rejects_a_missing_or_unauthorized_key(monkeypatch):
    with pytest.raises(ToolProviderCredentialValidationError, match="required"):
        YouComProvider()._validate_credentials({})

    class Client:
        def __init__(self, api_key):
            self.api_key = api_key

        def search(self, body, timeout):
            raise YouComError("You.com rejected the API key (401).", status_code=401)

    monkeypatch.setattr("provider.youdotcom.YouComClient", Client)
    with pytest.raises(ToolProviderCredentialValidationError, match="401") as caught:
        YouComProvider()._validate_credentials({"youdotcom_api_key": "secret-key"})
    assert "secret-key" not in str(caught.value)
