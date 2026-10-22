"""Client for the local UniFi Access developer API on a console.

Base URL: https://<console>:12445/api/v1/developer, header `Authorization: Bearer <token>`.
Every response is `{"code": "SUCCESS", "msg": "...", "data": ...}`; list endpoints
add `pagination: {page_num, page_size, total}`.

Endpoints used (UniFi Access API reference; license plates need Access 3.3.10+):
  GET    /users?page_num=&page_size=        list users (incl. license_plates)
  GET    /users/:id                         one user
  POST   /users                             create {first_name, last_name}
  DELETE /users/:id                         delete
  PUT    /users/:id/license_plates          assign ["AB-123-C", ...]
  DELETE /users/:id/license_plates/:id      unassign one plate
  GET    /user_groups                       list groups
  POST   /user_groups                       create {name}
  GET    /user_groups/:id/users/all         members of a group
  POST   /user_groups/:id/users             add [user_id, ...]
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import get_settings

PAGE_SIZE = 100


class AccessError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


@dataclass
class AccessUser:
    id: str
    first_name: str
    last_name: str
    status: str
    plates: list[dict[str, str]] = field(default_factory=list)  # {id, credential}

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "AccessUser":
        plates = [
            {"id": str(p.get("id", "")), "credential": str(p.get("credential", ""))}
            for p in data.get("license_plates") or []
            if p.get("credential")
        ]
        return cls(
            id=str(data["id"]),
            first_name=data.get("first_name") or "",
            last_name=data.get("last_name") or "",
            status=data.get("status") or "",
            plates=plates,
        )


class AccessClient:
    def __init__(self, base_url: str, token: str, verify_tls: bool = False, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/api/v1/developer",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            verify=verify_tls,
            timeout=15,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AccessClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            r = self._http.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise AccessError("connection_failed", str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise AccessError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise AccessError("http_error", str(exc)) from exc
        if r.status_code == 401:
            raise AccessError("unauthorized", "the API token was refused")
        if r.status_code == 403:
            raise AccessError("forbidden", "the API token lacks the required permission")
        if r.status_code == 404:
            raise AccessError("not_found", f"{method} {path}")
        try:
            body = r.json()
        except ValueError as exc:
            raise AccessError("invalid_response", f"HTTP {r.status_code}") from exc
        if r.status_code >= 400 or body.get("code") != "SUCCESS":
            raise AccessError(str(body.get("code") or f"HTTP_{r.status_code}"), str(body.get("msg") or ""))
        return body

    def probe(self) -> dict[str, int]:
        """Cheap read used by the console test: checks address, certificate and token."""
        body = self._call("GET", "/users", params={"page_num": 1, "page_size": 1})
        total = (body.get("pagination") or {}).get("total", len(body.get("data") or []))
        return {"users": int(total), "groups": len(self.list_groups())}

    # Users

    def list_users(self) -> list[AccessUser]:
        users: list[AccessUser] = []
        page = 1
        while True:
            body = self._call("GET", "/users", params={"page_num": page, "page_size": PAGE_SIZE})
            batch = body.get("data") or []
            users += [AccessUser.from_api(u) for u in batch]
            total = (body.get("pagination") or {}).get("total")
            if not batch or len(batch) < PAGE_SIZE or (total is not None and len(users) >= total):
                return users
            page += 1

    def get_user(self, user_id: str) -> AccessUser:
        return AccessUser.from_api(self._call("GET", f"/users/{user_id}")["data"])

    def create_user(self, first_name: str, last_name: str) -> AccessUser:
        data = self._call("POST", "/users", json={"first_name": first_name, "last_name": last_name})["data"]
        return AccessUser.from_api(data)

    def delete_user(self, user_id: str) -> None:
        self._call("DELETE", f"/users/{user_id}")

    def assign_plates(self, user_id: str, plates: list[str]) -> None:
        self._call("PUT", f"/users/{user_id}/license_plates", json=plates)

    def unassign_plate(self, user_id: str, plate_id: str) -> None:
        self._call("DELETE", f"/users/{user_id}/license_plates/{plate_id}")

    # Groups

    def list_groups(self) -> list[dict[str, str]]:
        data = self._call("GET", "/user_groups").get("data") or []
        return [{"id": str(g["id"]), "name": g.get("name") or ""} for g in data]

    def create_group(self, name: str) -> dict[str, str]:
        data = self._call("POST", "/user_groups", json={"name": name}).get("data")
        if isinstance(data, dict) and data.get("id"):
            return {"id": str(data["id"]), "name": data.get("name") or name}
        # Some versions return no body; look the new group up by name.
        for group in self.list_groups():
            if group["name"] == name:
                return group
        raise AccessError("group_not_created", name)

    def group_members(self, group_id: str) -> list[str]:
        data = self._call("GET", f"/user_groups/{group_id}/users/all").get("data") or []
        return [str(u["id"]) for u in data]

    def add_to_group(self, group_id: str, user_ids: list[str]) -> None:
        self._call("POST", f"/user_groups/{group_id}/users", json=user_ids)


def client_for(console: Any, token: str) -> AccessClient:
    transport = None
    if get_settings().access_mock:
        from .access_mock import transport_for

        transport = transport_for(console)
    return AccessClient(f"https://{console.host}:{console.port}", token, console.verify_tls, transport)
