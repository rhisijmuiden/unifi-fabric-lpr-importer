"""In-memory fake of the UniFi Access developer API, for tests and demos.

Enabled with LPR_ACCESS_MOCK=empty (no data) or LPR_ACCESS_MOCK=demo (a few
existing vehicles per console). One fake console exists per host name. The
token "invalid" is refused, like a revoked token on a real console.
"""

import json
import uuid
from typing import Any

import httpx

from ..config import get_settings


class FakeAccess:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.groups: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []

    # Helpers for tests and demo data

    def add_user(self, first_name: str, last_name: str, plates: list[str] = (), groups: list[str] = ()) -> str:
        uid = str(uuid.uuid4())
        self.users[uid] = {
            "id": uid,
            "first_name": first_name,
            "last_name": last_name,
            "status": "ACTIVE",
            "license_plates": [{"id": str(uuid.uuid4()), "credential": p, "credential_type": "license", "credential_status": "active"} for p in plates],
        }
        for name in groups:
            self._group(name)["members"].add(uid)
        return uid

    def _group(self, name: str) -> dict[str, Any]:
        for g in self.groups.values():
            if g["name"] == name:
                return g
        gid = str(uuid.uuid4())
        self.groups[gid] = {"id": gid, "name": name, "members": set()}
        return self.groups[gid]

    def plates(self) -> set[str]:
        return {p["credential"] for u in self.users.values() for p in u["license_plates"]}

    # HTTP handler

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") == "Bearer invalid":
            return httpx.Response(401, json={"code": "CODE_UNAUTHORIZED", "msg": "unauthorized"})
        path = request.url.path.removeprefix("/api/v1/developer")
        parts = [p for p in path.split("/") if p]
        method = request.method
        self.calls.append((method, path))
        body = json.loads(request.content) if request.content else None

        def ok(data: Any = None, **extra: Any) -> httpx.Response:
            return httpx.Response(200, json={"code": "SUCCESS", "msg": "success", "data": data, **extra})

        def missing() -> httpx.Response:
            return httpx.Response(200, json={"code": "CODE_NOT_EXISTS", "msg": "not found"})

        if parts == ["users"] and method == "GET":
            page = int(request.url.params.get("page_num", 1))
            size = int(request.url.params.get("page_size", 25))
            users = list(self.users.values())
            chunk = users[(page - 1) * size : page * size]
            return ok(chunk, pagination={"page_num": page, "page_size": size, "total": len(users)})
        if parts == ["users"] and method == "POST":
            uid = self.add_user(body["first_name"], body["last_name"])
            return ok(self.users[uid])
        if len(parts) >= 2 and parts[0] == "users":
            user = self.users.get(parts[1])
            if user is None:
                return missing()
            if len(parts) == 2 and method == "GET":
                return ok(user)
            if len(parts) == 2 and method == "DELETE":
                del self.users[parts[1]]
                for g in self.groups.values():
                    g["members"].discard(parts[1])
                return ok()
            if parts[2:] == ["license_plates"] and method == "PUT":
                taken = self.plates()
                for plate in body:
                    if plate in taken:
                        return httpx.Response(200, json={"code": "CODE_CREDS_LICENSE_PLATE_EXIST", "msg": "license plate already exists"})
                    user["license_plates"].append({"id": str(uuid.uuid4()), "credential": plate, "credential_type": "license", "credential_status": "active"})
                return ok()
            if len(parts) == 4 and parts[2] == "license_plates" and method == "DELETE":
                user["license_plates"] = [p for p in user["license_plates"] if p["id"] != parts[3]]
                return ok()
        if parts == ["user_groups"] and method == "GET":
            return ok([{"id": g["id"], "name": g["name"], "up_id": ""} for g in self.groups.values()])
        if parts == ["user_groups"] and method == "POST":
            g = self._group(body["name"])
            return ok({"id": g["id"], "name": g["name"]})
        if len(parts) >= 3 and parts[0] == "user_groups":
            group = self.groups.get(parts[1])
            if group is None:
                return missing()
            if parts[2:] == ["users", "all"] and method == "GET":
                return ok([self.users[u] for u in group["members"] if u in self.users])
            if parts[2:] == ["users"] and method == "POST":
                group["members"].update(body)
                return ok()
        return httpx.Response(404, json={"code": "CODE_NOT_FOUND", "msg": path})


_fakes: dict[str, FakeAccess] = {}

_DEMO = {
    0: [("Netwerktransport", "12-BDF-3", "Netwerktransport Wognum"), ("Netwerktransport", "VZ-482-K", "Netwerktransport Wognum"),
        ("Distributie", "98-BKL-1", "Distributie Wognum"), ("Onbekend", "Heftruck 3", "")],
    1: [("Netwerktransport", "12-BDF-3", "Netwerktransport Wognum"), ("Distributie", "41-VLP-7", "Distributie Zwaagdijk")],
    2: [("Netwerktransport", "VZ-482-K", "Netwerktransport Wognum")],
}


def fake_for(host: str) -> FakeAccess:
    if host not in _fakes:
        fake = FakeAccess()
        if get_settings().access_mock == "demo":
            for first, last, group in _DEMO[len(_fakes) % 3]:
                fake.add_user(first, last, [last] if "-" in last else [], [group] if group else [])
        _fakes[host] = fake
    return _fakes[host]


def reset() -> None:
    _fakes.clear()


def transport_for(console: Any) -> httpx.MockTransport:
    return httpx.MockTransport(fake_for(console.host).handle)
