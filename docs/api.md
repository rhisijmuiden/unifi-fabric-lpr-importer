# REST API for vehicle delivery (Lobster and other systems)

This guide is for the supplier of the system that delivers company vehicles, such as Lobster.
It describes version 1 of the API (`/api/v1`). Nederlandse versie: [api.nl.md](api.nl.md).

- Interactive reference: `http://<server>:8080/api/docs`, section **external API (v1)**
- Machine-readable specification (OpenAPI 3.1): [openapi-v1.json](openapi-v1.json), also live at `http://<server>:8080/api/openapi.json`

## Checklist for the supplier

1. Receive the server address and an API key from the administrator (see below).
2. Call `GET /api/v1/status` to test the connection and the key.
3. Send one vehicle with `"dry_run": true` and check the answer.
4. Deliver the vehicles with `POST /api/v1/vehicles` and an `Idempotency-Key` header.
5. Poll `GET /api/v1/jobs/{id}` until `status` is `done` or `failed`, and log the result.

## Authentication

An administrator creates an API key under **Administration › API keys**. The key starts with `lpr_` and is shown
once. Send it with every request:

```
Authorization: Bearer lpr_...
```

- Every change made with a key is written to the audit log under the key's name.
- A key without **Allow removing vehicles** can add and update, but cannot remove vehicles (`mode: "full"` and
  `DELETE` are refused).
- A key can be limited to **allowed addresses**: IP addresses or networks (CIDR, e.g. `203.0.113.10` or
  `10.20.0.0/16`). Requests from other addresses get `403 ip_not_allowed`. Give the administrator the public IP
  address(es) your system connects from.
- The application listens on port 8080. When the traffic crosses the internet, connect only through HTTPS
  (the installer can enable HTTPS on port 8080, or a reverse proxy is used) or a VPN; the administrator gives you
  the address to use. The key is a password: keep it out of logs and source code.
- Each key may make a limited number of requests per minute (default 600). Above that the API answers
  `429 too_many_requests` with a `Retry-After` header in seconds. An address that sends more than 30 wrong keys in a
  minute is paused for a minute in the same way.

## Vehicle fields

| Field | Required | Meaning |
| --- | --- | --- |
| `plate` | yes | License plate in any notation. Dutch plates are converted to the official notation (`12bdf3` → `12-BDF-3`). |
| `department` | yes | Department, e.g. `Netwerktransport` (max. 100 characters). Becomes the first name of the UniFi Access user. |
| `location` | no | Location (standplaats), e.g. `Wognum` (max. 100 characters). |
| `group_name` | no | UniFi Access user group (max. 200 characters). Default: department + location, e.g. `Netwerktransport Wognum`. |
| `description` | no | Free text, e.g. make and type. Cut off after 255 characters. An empty value keeps the existing description. |

In UniFi Access each vehicle becomes a user with first name = department, last name = plate, the plate as
credential, and membership of the group. Missing groups are created.

## Deliver vehicles

`POST /api/v1/vehicles`

```http
POST /api/v1/vehicles HTTP/1.1
Authorization: Bearer lpr_...
Content-Type: application/json
Idempotency-Key: 6f1c2a7e-3d4b-4c55-9a0e-1b2c3d4e5f60

{
  "vehicles": [
    { "plate": "12-BDF-3", "department": "Netwerktransport", "location": "Wognum", "description": "DAF XF" },
    { "plate": "VZ-482-K", "department": "Netwerktransport", "location": "Zwaagdijk" }
  ],
  "mode": "upsert",
  "dry_run": false
}
```

| Field | Default | Meaning |
| --- | --- | --- |
| `vehicles` | | 1 to 20,000 vehicles. |
| `mode` | `upsert` | `upsert` adds and updates only. `full` also removes vehicles of the **same departments** that are no longer in the list, from the application and from every console. `full` needs a key that may remove. |
| `consoles` | all | List of console names or ids to register on. Omitted = all active consoles; `[]` = store in the app only. |
| `dry_run` | `false` | `true` returns what would change without changing anything. |

Response `202 Accepted`:

```json
{ "job_id": 42, "status": "queued", "status_url": "/api/v1/jobs/42", "replayed": false }
```

Rows with an invalid plate, a missing department, a value that is too long or a duplicate plate are skipped; the
other rows are processed. With `dry_run` the response is `200 OK` with a `summary` (counts of `new`, `changed`,
`unchanged`, `invalid`), the `remove` list in full mode, and the skipped rows under `invalid` with their `error`
(`invalid_plate`, `missing_department`, `too_long`, `duplicate`).

### Idempotency and retries

Send an `Idempotency-Key` header with a unique value per delivery (for example a UUID, max. 100 characters). If
the connection drops and you send the same request again with the same key within 24 hours, no second job is
started: the answer is `200 OK` with the original `job_id` and `"replayed": true`. Use a new value for every new
delivery.

Retry on network errors and on status `502`, `503` and `504`, with a growing pause (for example 10 s, 30 s,
2 min). Do not retry `4xx` answers without fixing the request.

### Following a job

`GET /api/v1/jobs/42`

```json
{
  "id": 42, "kind": "import", "actor": "Lobster", "status": "done",
  "total": 6, "processed": 6, "succeeded": 6, "failed": 0,
  "result": { "vehicles": 2, "skipped": 0, "assign": { "...": "..." } },
  "created_at": "2026-10-22T08:00:00+00:00", "finished_at": "2026-10-22T08:00:09+00:00",
  "log": [ { "at": "...", "ok": true, "message": "Wognum: 12-BDF-3: user_created, plate_assigned" } ]
}
```

- `status`: `queued` → `running` → `done` or `failed`. Changes on the consoles run one job at a time, so a job
  can stay `queued` for a while when another import is running.
- `processed`, `succeeded`, `failed`: one step per vehicle per console.
- `done` with `failed > 0` means some steps failed (for example a console that was offline); the `log` says which.
- Poll every 2 to 5 seconds. A key only sees its own jobs.

The administrator can receive a mail with the import report or only when something failed (**Administration ›
Notifications**).

## Other calls

| Call | Purpose |
| --- | --- |
| `GET /api/v1/status` | Connection test: key name, whether it may remove, application version, number of active consoles |
| `GET /api/v1/vehicles` | All vehicles with the consoles they are present on. Optional filters `?department=` and `?location=` |
| `GET /api/v1/vehicles/{plate}` | One vehicle, plate in any notation |
| `DELETE /api/v1/vehicles/{plate}` | Remove one vehicle from every console and from the app (key must allow removing); answers with a job like `POST` |
| `GET /api/v1/consoles` | Active consoles (id, name, location) |
| `GET /api/v1/jobs/{id}` | Status and report of a job started with this key |

## Errors

Errors are JSON with a `detail` field.

| Status | `detail` | Meaning |
| --- | --- | --- |
| 400 | `unknown_console:<name>` | A console in `consoles` does not exist or is inactive |
| 401 | `invalid_api_key` | Key missing, wrong or disabled |
| 403 | `ip_not_allowed` | The request comes from an address the key may not be used from |
| 403 | `delete_not_allowed` | The key may not remove vehicles |
| 404 | `not_found` | Vehicle or job not found |
| 422 | (list) | The request body does not match the schema, e.g. more than 20,000 vehicles |
| 429 | `too_many_requests` | Rate limit reached; retry after the number of seconds in `Retry-After` |

## Examples

```bash
# Connection test
curl http://lpr.example.local:8080/api/v1/status -H "Authorization: Bearer lpr_..."

# Delivery
curl -X POST http://lpr.example.local:8080/api/v1/vehicles \
  -H "Authorization: Bearer lpr_..." \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"vehicles":[{"plate":"12-BDF-3","department":"Netwerktransport","location":"Wognum"}]}'

# Status
curl http://lpr.example.local:8080/api/v1/jobs/42 -H "Authorization: Bearer lpr_..."
```

## Versioning

Fields may be added to answers within `/api/v1`; ignore fields you do not know. Breaking changes get a new path
(`/api/v2`), and `/api/v1` keeps working during a transition period.
