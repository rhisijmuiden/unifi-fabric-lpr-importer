# Roadmap

Living version with comments: https://claude.ai/artifact/4DLNJHm272aJB5THzPhRRx

Target platform: Debian 13, UniFi Protect 7.3, UniFi Access 4.2+ (plate support since 3.3.10), 3 locations in one UniFi Fabric.

Integration: the official cloud APIs (Protect, Site Manager, Network) have no vehicle or license plate endpoints. Plates are linked to users through the local UniFi Access API on each console (HTTPS port 12445, Bearer token per console); Access 3.3.10+ supports assigning and unassigning license plates to users.
Stack: Python 3.13 + FastAPI, PostgreSQL 17 + Alembic, React + Vite + Tailwind CSS, react-i18next, systemd, port 8080.

Each phase ends with a release on `test`; after approval it is merged into `main`.

## Phase 0 – Foundation and proof of concept
- [x] Git repository with `main` (production) and `test` branches
- [ ] Proof of concept: create one Access user (vehicle), assign and unassign a license plate through the Access API, verify the gate opens
- [x] Minimum versions: UniFi Protect 7.3, UniFi Access 4.2
- **Gate:** assigning plates through the Access API works

## Phase 1 – Foundation
- [x] Debian 13 installer (`install.sh`): packages, PostgreSQL, system user, systemd, port 8080
- [x] Admin layout with left sidebar, light/dark theme, RHIS house style
- [x] Local login, users and roles (admin, operator, read-only)
- [x] English and Dutch translations
- [x] Info button: version, branch, commit, update check
- [x] Update from the UI and switch between production and test (database snapshot before update, rollback on failure)
- [x] Microsoft Entra SSO on/off, groups mapped to roles, local admin emergency access
- [x] Custom SMTP server: STARTTLS/SSL, password or OAuth2 (Microsoft 365), test mail
- [x] Audit log

## Phase 2 – Consoles and vehicles
- [x] Add console with step-by-step help (where to find the address and Access API token) and a test button
- [x] Read existing UniFi Access users and plates and adopt them into the app
- [x] Naming convention: first name = department, last name = plate in capitals, group = department + location
- [x] CSV import wizard: field mapping and conversion, filter (e.g. by location), assign filtered vehicles to a group; the group is created if missing and the UniFi Fabric distributes it
- [x] Only plate and department required; vehicles sorted by group automatically
- [x] Vehicle overview with present / not present per console; select several vehicles and "assign to"
- [x] Batch processing in the background with progress and report
- [x] Full sync with dry-run
- [x] Statistics page: totals per department, group and console
- [x] Audit every add and delete in UniFi with who did it (user or API key)
- [ ] Live test against a real console (needs an Access API token)

## Phase 3 – Backup and restore
- [x] Full and incremental backup of all data (vehicles, consoles, users, settings, API keys, audit log) and the secret key
- [x] Remote locations: SCP/SFTP (password or the app's own SSH key, pinned host key), FTPS (explicit/implicit TLS), FTP; several locations at once
- [x] AES-256-GCM encryption with a passphrase; retention per location (number of full backups with their incrementals)
- [x] Schedules per backup type (hourly, daily, weekly, monthly) and mail on failure or after every backup
- [x] Restore from a location or from uploaded files, older backups are migrated to the current schema; a local copy is made first
- [x] Restore on a fresh server: `install.sh --restore` or `python -m app.cli restore`
- [ ] Live test against the real backup server

## Phase 4 – API integration (Lobster)
- [x] REST API with API keys, same conversion and batch path as the CSV import (built in phase 2)
- [x] OpenAPI docs and an integration guide (EN/NL): `docs/api.md`, `docs/api.nl.md`, published spec `docs/openapi-v1.json`
- [x] Hardening: connection test (`GET /api/v1/status`), `Idempotency-Key` for safe retries, IP allowlist per API key, one console job at a time, per-row length checks
- [x] Lookup of one vehicle and filters by department and location
- [x] Mail notifications: import report, failed sync, available update (Administration › Notifications)
- [ ] Live test with Lobster

## Phase 5 – v1.0
- [ ] Scheduled imports
- [ ] Dashboard with status per location and recent syncs
- [ ] Security hardening: rate limiting, session management, encrypted secrets
- [ ] Tests, manual (EN/NL), release v1.0 on `main`
