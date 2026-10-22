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
- [ ] Add console with step-by-step help (where to find the address and Access API token) and a test button
- [ ] Read existing UniFi Access users and plates and adopt them into the app
- [ ] Naming convention: first name = department, last name = plate in capitals, group = department + location
- [ ] CSV import wizard: field mapping and conversion, filter (e.g. by location), assign filtered vehicles to a group; the group is created if missing and the UniFi Fabric distributes it
- [ ] Only plate and department required; vehicles sorted by group automatically
- [ ] Vehicle overview with present / not present per console; select several vehicles and "assign to"
- [ ] Batch processing in the background with progress and report
- [ ] Full sync with dry-run
- [ ] Statistics page: totals per department, group and console
- [ ] Audit every add and delete in UniFi with who did it (user or API key)

## Phase 3 – Backup and restore
- [ ] Full and incremental backup (database, configuration, files)
- [ ] Remote targets: FTP, FTPS, SCP; encryption and retention
- [ ] Schedules per backup type
- [ ] Restore from remote, also on a fresh server through the installer

## Phase 4 – API integration (Lobster)
- [ ] REST API with API keys, same conversion and batch path as the CSV import
- [ ] OpenAPI docs and an integration guide (EN/NL)
- [ ] Mail notifications: import report, failed sync, available update

## Phase 5 – v1.0
- [ ] Scheduled imports
- [ ] Dashboard with status per location and recent syncs
- [ ] Security hardening: rate limiting, session management, encrypted secrets
- [ ] Tests, manual (EN/NL), release v1.0 on `main`
