# Roadmap

Living version with comments: https://claude.ai/artifact/4DLNJHm272aJB5THzPhRRx

Target platform: Debian 13, UniFi Protect 7.3, UniFi Access 4.2+ (plate support since 3.3.10), 3 locations in one UniFi Fabric.

Integration: the official cloud APIs (Protect, Site Manager, Network) have no vehicle or license plate endpoints. Plates are linked to users through the local UniFi Access API on each console (HTTPS port 12445, Bearer token per console); Access 3.3.10+ supports assigning and unassigning license plates to users.
Stack: Python 3.13 + FastAPI, PostgreSQL 17 + Alembic, React + Vite + Tailwind + shadcn/ui, react-i18next, systemd, port 8080.

Each phase ends with a release on `test`; after approval it is merged into `main`.

## Phase 0 – Foundation and proof of concept
- [x] Git repository with `main` (production) and `test` branches
- [ ] Proof of concept: create one Access user (vehicle), assign and unassign a license plate through the Access API, verify the gate opens
- [x] Minimum versions: UniFi Protect 7.3, UniFi Access 4.2
- **Gate:** assigning plates through the Access API works

## Phase 1 – Base platform
- [ ] Debian 13 installer (`install.sh`): packages, PostgreSQL, system user, systemd, port 8080
- [ ] Admin layout with left sidebar, light/dark theme, responsive
- [ ] Local admin login, users and roles (admin, operator, read-only)
- [ ] English and Dutch translations from the start
- [ ] Info button: version, branch, commit, update check
- [ ] Update from the UI and switch between production and test (automatic backup before update)

## Phase 2 – Vehicle import
- [ ] Console management: address and Access API token per location, connection test, Access version check
- [ ] CSV import (and XLSX) with column mapping, validation, duplicates and preview
- [ ] REST API with API keys for Lobster and other systems, OpenAPI docs and an integration guide (EN/NL)
- [ ] Dry-run showing the changes per location
- [ ] Full sync: vehicles missing from the source are removed
- [ ] Vehicle overview: list of all known plates with one column per console showing present / not present (read live), plus search, filters, labels and expiry date; re-sync a missing plate from the list
- [ ] Audit log

## Phase 3 – SSO and mail
- [ ] Microsoft Entra SSO on/off, groups mapped to roles, local emergency account
- [ ] Custom SMTP server: STARTTLS/SSL, password or OAuth2, test mail
- [ ] Notifications: import report, failed sync, backup status, available update

## Phase 4 – Backup and restore
- [ ] Full backup: database, configuration, uploaded files
- [ ] Incremental backup
- [ ] Remote targets: FTP, FTPS, SCP; encryption and retention
- [ ] Schedules per backup type
- [ ] Restore from remote, also on a fresh server through the installer

## Phase 5 – v1.0
- [ ] Scheduled imports
- [ ] Dashboard with status per location and recent syncs
- [ ] Security hardening: rate limiting, session management, encrypted secrets
- [ ] Tests, manual (EN/NL), release v1.0 on `main`
