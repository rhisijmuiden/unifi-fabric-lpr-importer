"""Microsoft Entra ID single sign-on (OpenID Connect authorization code flow with PKCE)."""

import secrets
import time
from typing import Any

import msal

from ..config import get_settings

SCOPES = ["User.Read"]
_FLOW_TTL = 600
_flows: dict[str, tuple[float, dict[str, Any]]] = {}


class SsoError(Exception):
    pass


def redirect_uri() -> str:
    return get_settings().base_url.rstrip("/") + "/api/auth/sso/callback"


def _app(cfg: dict[str, Any]) -> msal.ConfidentialClientApplication:
    if not (cfg.get("tenant_id") and cfg.get("client_id") and cfg.get("client_secret")):
        raise SsoError("Single sign-on is not fully configured")
    return msal.ConfidentialClientApplication(
        cfg["client_id"],
        authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}",
        client_credential=cfg["client_secret"],
    )


def _prune() -> None:
    now = time.time()
    for key in [k for k, (ts, _) in _flows.items() if now - ts > _FLOW_TTL]:
        _flows.pop(key, None)


def start(cfg: dict[str, Any]) -> tuple[str, str]:
    """Return (flow_key, authorization_url). The key goes in a short-lived cookie."""
    _prune()
    flow = _app(cfg).initiate_auth_code_flow(SCOPES, redirect_uri=redirect_uri())
    key = secrets.token_urlsafe(24)
    _flows[key] = (time.time(), flow)
    return key, flow["auth_uri"]


def finish(cfg: dict[str, Any], key: str | None, params: dict[str, str]) -> dict[str, Any]:
    """Complete the flow and return the ID token claims."""
    _prune()
    entry = _flows.pop(key or "", None)
    if entry is None:
        raise SsoError("Sign-in expired, please try again")
    result = _app(cfg).acquire_token_by_auth_code_flow(entry[1], params)
    if "error" in result:
        raise SsoError(result.get("error_description") or result["error"])
    return result.get("id_token_claims") or {}


def role_for_claims(cfg: dict[str, Any], claims: dict[str, Any]) -> str | None:
    """Map Entra group membership to an app role; the highest role wins.

    Requires the app registration to emit the `groups` claim in the ID token.
    """
    groups = set(claims.get("groups") or [])
    for role in ("admin", "operator", "viewer"):
        group_id = (cfg.get(f"{role}_group_id") or "").strip()
        if group_id and group_id in groups:
            return role
    return None
