# REST API for vehicle delivery (Lobster and other systems)

This guide is for the supplier of the system that delivers company vehicles, such as Lobster.
The interactive reference (OpenAPI) is at `https://<server>:8080/api/docs`, section **external API (v1)**.

## Authentication

An administrator creates an API key under **Administration › API keys**. The key starts with `lpr_` and is shown
once. Send it with every request:

```
Authorization: Bearer lpr_...
```

Every change made with a key is written to the audit log under the key's name. A key without
**Allow removing vehicles** can add and update, but cannot remove vehicles.

## Vehicle fields

| Field | Required | Meaning |
| --- | --- | --- |
| `plate` | yes | License plate. Dutch plates are converted to the official notation (`12bdf3` → `12-BDF-3`). |
| `department` | yes | Department, e.g. `Netwerktransport`. Becomes the first name of the UniFi Access user. |
| `location` | no | Location (standplaats), e.g. `Wognum`. |
| `group_name` | no | UniFi Access user group. Default: department + location, e.g. `Netwerktransport Wognum`. |
| `description` | no | Free text, e.g. make and type. |

In UniFi Access each vehicle becomes a user with first name = department, last name = plate, the plate as
credential, and membership of the group. Missing groups are created.

## Deliver vehicles

`POST /api/v1/vehicles`

```json
{
  "vehicles": [
    { "plate": "12-BDF-3", "department": "Netwerktransport", "location": "Wognum", "description": "DAF XF" },
    { "plate": "VZ-482-K", "department": "Netwerktransport", "location": "Zwaagdijk" }
  ],
  "mode": "upsert",
  "dry_run": false
}
```

- `mode`: `upsert` (default) adds and updates only. `full` also removes vehicles of the **same departments** that
  are no longer in the list, from the application and from every console. `full` needs a key that may remove.
- `consoles`: optional list of console names or ids. Omitted = all active consoles; `[]` = store in the app only.
- `dry_run`: `true` returns what would change without changing anything.

Response `202 Accepted`:

```json
{ "job_id": 42, "status": "queued", "status_url": "/api/v1/jobs/42" }
```

The vehicles are registered in the background. Poll the status URL:

`GET /api/v1/jobs/42` → `status` is `queued`, `running`, `done` or `failed`, with counters `processed`,
`succeeded`, `failed` and a `log` with one line per vehicle per console.

Rows with an invalid plate, a missing department or a duplicate plate are skipped; `dry_run` lists them under
`invalid`.

## Other calls

| Call | Purpose |
| --- | --- |
| `GET /api/v1/vehicles` | All vehicles, with the consoles they are present on |
| `DELETE /api/v1/vehicles/{plate}` | Remove one vehicle from every console and from the app (key must allow removing) |
| `GET /api/v1/consoles` | Active consoles (id, name, location) |
| `GET /api/v1/jobs/{id}` | Status of a job started with this key |

## Errors

| Status | `detail` | Meaning |
| --- | --- | --- |
| 401 | `invalid_api_key` | Key missing, wrong or disabled |
| 403 | `delete_not_allowed` | The key may not remove vehicles |
| 400 | `unknown_console:<name>` | A console in `consoles` does not exist or is inactive |
| 404 | `not_found` | Vehicle or job not found |
| 422 | (list) | The request body does not match the schema |

## Example

```bash
curl -X POST https://lpr.example.local:8080/api/v1/vehicles \
  -H "Authorization: Bearer lpr_..." \
  -H "Content-Type: application/json" \
  -d '{"vehicles":[{"plate":"12-BDF-3","department":"Netwerktransport","location":"Wognum"}]}'
```
