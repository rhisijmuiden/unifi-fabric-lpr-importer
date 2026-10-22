"""Reading and changing vehicles on the consoles through UniFi Access.

Naming convention for a vehicle user in Access:
  first name = department, last name = plate (official notation),
  user group = department + location, e.g. "Netwerktransport Wognum".
Every change on a console is written to the audit log with the actor.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit
from ..models import Console, ConsolePlate, Vehicle
from ..security import decrypt
from ..settings_store import get_section
from .access import AccessClient, AccessError, AccessUser, client_for
from .jobs import JobContext
from .plates import credential_value, format_plate, group_name, plate_key


def open_client(console: Console) -> AccessClient:
    return client_for(console, decrypt(console.api_token) or "")


@dataclass
class ConsoleState:
    """Live view of one console, loaded once per job."""

    client: AccessClient
    users: dict[str, AccessUser]
    by_plate: dict[str, tuple[AccessUser, dict[str, str]]]
    groups: dict[str, str]  # name -> id
    members: dict[str, set[str]] = field(default_factory=dict)  # group id -> user ids

    @classmethod
    def load(cls, client: AccessClient) -> "ConsoleState":
        users = {u.id: u for u in client.list_users()}
        state = cls(client, users, {}, {g["name"]: g["id"] for g in client.list_groups()})
        state._index()
        return state

    def _index(self) -> None:
        self.by_plate = {plate_key(p["credential"]): (u, p) for u in self.users.values() for p in u.plates}

    def group_members(self, group_id: str) -> set[str]:
        if group_id not in self.members:
            self.members[group_id] = set(self.client.group_members(group_id))
        return self.members[group_id]

    def groups_of(self, user_id: str) -> list[str]:
        return sorted(name for name, gid in self.groups.items() if user_id in self.group_members(gid))

    def refresh_user(self, user_id: str) -> AccessUser:
        user = self.client.get_user(user_id)
        self.users[user_id] = user
        self._index()
        return user


def _snapshot(db: Session, console: Console, user: AccessUser, plate: dict[str, str], groups: list[str]) -> None:
    key = plate_key(plate["credential"])
    row = db.scalar(select(ConsolePlate).where(ConsolePlate.console_id == console.id, ConsolePlate.plate_key == key))
    if row is None:
        row = ConsolePlate(console_id=console.id, plate_key=key)
        db.add(row)
    row.credential = plate["credential"]
    row.plate_id = plate["id"]
    row.user_id = user.id
    row.first_name = user.first_name
    row.last_name = user.last_name
    row.groups = groups
    row.seen_at = datetime.now(timezone.utc)


def _consoles(db: Session, console_ids: list[int] | None) -> list[Console]:
    stmt = select(Console).where(Console.is_active).order_by(Console.sort_order, Console.name)
    if console_ids is not None:  # None = all active consoles
        stmt = stmt.where(Console.id.in_(console_ids))
    return list(db.scalars(stmt))


# Scan


def scan(ctx: JobContext, console_ids: list[int] | None = None) -> dict[str, Any]:
    db = ctx.db
    consoles = _consoles(db, console_ids)
    ctx.add_total(len(consoles))
    result: dict[str, Any] = {}
    for console in consoles:
        try:
            with open_client(console) as client:
                state = ConsoleState.load(client)
                db.execute(delete(ConsolePlate).where(ConsolePlate.console_id == console.id))
                for key, (user, plate) in state.by_plate.items():
                    _snapshot(db, console, user, plate, state.groups_of(user.id))
                console.last_scan_at = datetime.now(timezone.utc)
                db.commit()
            result[console.name] = len(state.by_plate)
            audit.record(db, "console.scanned", target=console.name, details={"plates": len(state.by_plate), "users": len(state.users)}, **ctx.actor.audit())
            ctx.step(True, f"{console.name}: {len(state.by_plate)} plates", console=console.name, plates=len(state.by_plate))
        except AccessError as exc:
            db.rollback()
            audit.record(db, "console.scanned", target=console.name, success=False, message=str(exc), **ctx.actor.audit())
            ctx.step(False, f"{console.name}: {exc}", console=console.name, code=exc.code)
    return {"plates": result}


# Assign


def _ensure_on_console(db: Session, ctx: JobContext, console: Console, state: ConsoleState, vehicle: Vehicle, notation: str) -> str:
    """Make sure the vehicle exists on the console per the naming convention. Returns what changed."""
    actor = ctx.actor.audit()
    key = vehicle.plate_key
    changes: list[str] = []
    found = state.by_plate.get(key)
    if found:
        user = found[0]
    else:
        # Reuse a convention user without the plate (e.g. after the plate was unassigned by hand).
        user = next(
            (u for u in state.users.values() if plate_key(u.last_name) == key and u.first_name == vehicle.department),
            None,
        )
        if user is None:
            user = state.client.create_user(vehicle.department or vehicle.group_name or "Vehicle", format_plate(vehicle.plate))
            state.users[user.id] = user
            changes.append("user_created")
            audit.record(db, "access.user_created", target=f"{console.name}: {user.first_name} {user.last_name}", details={"console": console.name, "user_id": user.id, "plate": vehicle.plate}, **actor)
        state.client.assign_plates(user.id, [credential_value(vehicle.plate, notation)])
        user = state.refresh_user(user.id)
        changes.append("plate_assigned")
        audit.record(db, "access.plate_assigned", target=vehicle.plate, details={"console": console.name, "user_id": user.id}, **actor)

    if vehicle.group_name:
        gid = state.groups.get(vehicle.group_name)
        if gid is None:
            gid = state.client.create_group(vehicle.group_name)["id"]
            state.groups[vehicle.group_name] = gid
            state.members[gid] = set()
            changes.append("group_created")
            audit.record(db, "access.group_created", target=f"{console.name}: {vehicle.group_name}", details={"console": console.name, "group_id": gid}, **actor)
        members = state.group_members(gid)
        if user.id not in members:
            state.client.add_to_group(gid, [user.id])
            members.add(user.id)
            changes.append("group_assigned")
            audit.record(db, "access.group_member_added", target=vehicle.plate, details={"console": console.name, "group": vehicle.group_name, "user_id": user.id}, **actor)

    plate = state.by_plate.get(key)
    if plate:
        _snapshot(db, console, plate[0], plate[1], state.groups_of(user.id))
    db.commit()
    return ", ".join(changes) or "unchanged"


def assign(ctx: JobContext, vehicle_ids: list[int], console_ids: list[int] | None = None) -> dict[str, Any]:
    db = ctx.db
    consoles = _consoles(db, console_ids)
    vehicles = list(db.scalars(select(Vehicle).where(Vehicle.id.in_(vehicle_ids)).order_by(Vehicle.group_name, Vehicle.plate)))
    notation = get_section(db, "access")["plate_notation"]
    ctx.add_total(len(consoles) * len(vehicles))
    summary: dict[str, dict[str, int]] = {}
    for console in consoles:
        counts = summary.setdefault(console.name, {"changed": 0, "unchanged": 0, "failed": 0})
        client = open_client(console)
        try:
            state = ConsoleState.load(client)
        except AccessError as exc:
            client.close()
            for vehicle in vehicles:
                counts["failed"] += 1
                ctx.step(False, f"{console.name}: {vehicle.plate}: {exc}", console=console.name, plate=vehicle.plate, code=exc.code)
            continue
        with client:
            for vehicle in vehicles:
                try:
                    what = _ensure_on_console(db, ctx, console, state, vehicle, notation)
                    counts["unchanged" if what == "unchanged" else "changed"] += 1
                    ctx.step(True, f"{console.name}: {vehicle.plate}: {what}", console=console.name, plate=vehicle.plate)
                except AccessError as exc:
                    db.rollback()
                    counts["failed"] += 1
                    audit.record(db, "access.plate_assigned", target=vehicle.plate, success=False, message=str(exc), details={"console": console.name}, **ctx.actor.audit())
                    ctx.step(False, f"{console.name}: {vehicle.plate}: {exc}", console=console.name, plate=vehicle.plate, code=exc.code)
    return {"consoles": summary}


# Remove


def _remove_from_console(db: Session, ctx: JobContext, console: Console, state: ConsoleState, key: str, label: str, delete_users: bool) -> str:
    actor = ctx.actor.audit()
    found = state.by_plate.get(key)
    if not found:
        db.execute(delete(ConsolePlate).where(ConsolePlate.console_id == console.id, ConsolePlate.plate_key == key))
        db.commit()
        return "not_present"
    user, plate = found
    state.client.unassign_plate(user.id, plate["id"])
    audit.record(db, "access.plate_removed", target=label, details={"console": console.name, "user_id": user.id}, **actor)
    what = "plate_removed"
    others = [p for p in user.plates if p["id"] != plate["id"]]
    # Only users that are a vehicle by convention (last name = this plate) are deleted.
    if delete_users and not others and plate_key(user.last_name) == key:
        state.client.delete_user(user.id)
        state.users.pop(user.id, None)
        audit.record(db, "access.user_deleted", target=f"{console.name}: {user.first_name} {user.last_name}", details={"console": console.name, "user_id": user.id}, **actor)
        what = "user_deleted"
    else:
        user.plates = others
    state.by_plate.pop(key, None)
    db.execute(delete(ConsolePlate).where(ConsolePlate.console_id == console.id, ConsolePlate.plate_key == key))
    db.commit()
    return what


def remove(ctx: JobContext, plate_keys: list[str], console_ids: list[int] | None = None, delete_vehicles: bool = False) -> dict[str, Any]:
    db = ctx.db
    consoles = _consoles(db, console_ids)
    delete_users = bool(get_section(db, "access")["delete_vehicle_users"])
    labels = {v.plate_key: v.plate for v in db.scalars(select(Vehicle).where(Vehicle.plate_key.in_(plate_keys)))}
    ctx.add_total(len(consoles) * len(plate_keys))
    failed_keys: set[str] = set()
    for console in consoles:
        client = open_client(console)
        try:
            state = ConsoleState.load(client)
        except AccessError as exc:
            client.close()
            for key in plate_keys:
                failed_keys.add(key)
                ctx.step(False, f"{console.name}: {labels.get(key, key)}: {exc}", console=console.name, code=exc.code)
            continue
        with client:
            for key in plate_keys:
                label = labels.get(key, key)
                try:
                    what = _remove_from_console(db, ctx, console, state, key, label, delete_users)
                    ctx.step(True, f"{console.name}: {label}: {what}", console=console.name, plate=label)
                except AccessError as exc:
                    db.rollback()
                    failed_keys.add(key)
                    audit.record(db, "access.plate_removed", target=label, success=False, message=str(exc), details={"console": console.name}, **ctx.actor.audit())
                    ctx.step(False, f"{console.name}: {label}: {exc}", console=console.name, plate=label, code=exc.code)
    deleted = 0
    if delete_vehicles:
        # A vehicle stays in the app while a console still holds its plate.
        for vehicle in db.scalars(select(Vehicle).where(Vehicle.plate_key.in_(set(plate_keys) - failed_keys))):
            db.delete(vehicle)
            deleted += 1
            audit.record(db, "vehicle.deleted", target=vehicle.plate, commit=False, **ctx.actor.audit())
        db.commit()
    return {"removed": len(plate_keys) - len(failed_keys), "failed": len(failed_keys), "vehicles_deleted": deleted}


# Adopt plates found on consoles


def adopt_candidates(db: Session) -> list[dict[str, Any]]:
    """Plates on a console that the app does not manage yet, with a suggested department/location."""
    known = set(db.scalars(select(Vehicle.plate_key)))
    rows = db.scalars(select(ConsolePlate).join(Console).order_by(Console.sort_order, ConsolePlate.plate_key))
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.plate_key in known:
            continue
        item = found.get(row.plate_key)
        if item is None:
            item = found[row.plate_key] = {"plate_key": row.plate_key, "plate": format_plate(row.credential), **_suggest(row), "consoles": []}
        item["consoles"].append(row.console.name)
    return list(found.values())


def _suggest(row: ConsolePlate) -> dict[str, str]:
    convention = plate_key(row.last_name) == row.plate_key
    department = row.first_name if convention else ""
    location = row.console.location
    group = ""
    for name in row.groups:
        if department and name.startswith(department + " "):
            location, group = name[len(department) + 1 :], name
            break
    if not group and row.groups:
        group = row.groups[0]
    return {
        "department": department,
        "location": location,
        "group_name": group or group_name(department, location),
        "user_name": f"{row.first_name} {row.last_name}".strip(),
        "follows_convention": convention,
    }
