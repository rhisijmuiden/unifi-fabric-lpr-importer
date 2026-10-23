import httpx
import pytest

from app.services import access
from app.services.access import AccessClient, AccessError


def client(handler):
    return AccessClient("https://console:12445", "token", transport=httpx.MockTransport(handler))


def test_delete_user_deactivates_first():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, request.content))
        return httpx.Response(200, json={"code": "SUCCESS", "msg": "success", "data": None})

    client(handler).delete_user("u1")
    assert [(m, p) for m, p, _ in calls] == [("PUT", "/api/v1/developer/users/u1"), ("DELETE", "/api/v1/developer/users/u1")]
    assert b"DEACTIVATED" in calls[0][2]


def test_retries_429_then_gives_up(monkeypatch):
    monkeypatch.setattr(access.time, "sleep", lambda s: None)
    answers = [429, 200]

    def handler(request):
        code = answers.pop(0) if answers else 429
        return httpx.Response(code, json={"code": "SUCCESS", "msg": "success", "data": []})

    assert client(handler).list_groups() == []
    with pytest.raises(AccessError) as exc:
        client(handler).list_groups()
    assert exc.value.code == "rate_limited"


def test_identity_enterprise_code_is_named():
    def handler(request):
        return httpx.Response(200, json={"code": "CODE_OTHERS_UID_ADOPTED_NOT_SUPPORTED", "msg": "not available"})

    with pytest.raises(AccessError) as exc:
        client(handler).probe()
    assert exc.value.code == "identity_enterprise"
