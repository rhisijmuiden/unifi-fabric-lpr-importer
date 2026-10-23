# Changelog

## 1.0.1 – 2026-10-23

### Fixed
- **Installer on containers without a locale** (such as the Debian 13 LXC template): the database is now always
  created as UTF8 (`-E UTF8 -T template0 --locale=C.UTF-8`) instead of SQL_ASCII, so step 7 (database migrations)
  no longer fails. An empty SQL_ASCII database left behind by an earlier failed run is recreated.
- The install instructions are one line that installs curl first, which a minimal Debian 13 image does not have;
  the installer itself also installs curl (and whiptail) before its first step.

## 1.0.0 – 2026-10-23

First production release.

### Added
- **Scheduled imports**: fetch a CSV file from a web address (HTTPS, optional basic authentication) or an SCP/SFTP,
  FTPS or FTP server on an hourly, daily, weekly or monthly schedule, with the wizard's column mapping, fixed values
  and a location/department filter. Unchanged files are skipped, a file without valid vehicles never imports, and a
  full sync stops without changes when it would remove more vehicles than the set limit. Test button shows the
  columns and what an import would do.
- **Automatic console reads** (hourly by default) so presence on every console stays current.
- **Dashboard**: status per location (in order / attention / problem) with coverage, last read, last change,
  changes in 7 days, failures in 24 hours and the last error; recent syncs with their source; scheduled imports;
  last backup.
- **Security page**: session length and idle timeout, sign-in lockout, REST API rate limit, server checks (HTTPS,
  secure cookies, secret key) and all signed-in sessions with sign-out.
- **My sessions** for every user (click your name): see and sign out other browsers.
- **HTTPS on port 8080** from the installer, with a self-signed or your own certificate (`--https`, `--cert/--key`).
- **Graphical installer** (whiptail): dialogs for channel, HTTP/HTTPS and restore, a progress bar with "step X of 10",
  an error screen with the log, and the address and first password at the end. `--unattended` for scripts.
- Manual in English and Dutch (`docs/manual.md`, `docs/manual.nl.md`).

### Security
- Rate limiting: 5 failed sign-ins lock a user name for 15 minutes (an IP address after 20); 600 API requests per
  minute per key; addresses sending many wrong API keys are paused. Answers `429` with `Retry-After`.
- Sessions record IP address, browser and last activity; idle sessions end after 60 minutes. A password change ends
  the user's other sessions; a role change, a disabled account or a password reset by an admin ends all of them.
- Security headers on every response (Content-Security-Policy, X-Frame-Options, nosniff, Referrer-Policy, HSTS with
  HTTPS) and `Cache-Control: no-store` on the API.
- The application refuses to start on PostgreSQL with the example secret key; the Security page warns about a weak one.
- Sign-in takes the same time for unknown user names. Passwords of scheduled imports are encrypted like other secrets
  and re-encrypted on restore.
- systemd unit hardened (ProtectHome, ProtectKernelTunables, ProtectControlGroups).

### Changed
- Import reports also cover scheduled imports.
- Remote file access no longer creates missing folders when only reading (scheduled imports).

## 0.4.0
Lobster REST API hardening: status endpoint, Idempotency-Key, IP allowlist per key, serialized console jobs, mail
notifications (import report, failed sync, update available), OpenAPI document and supplier guide (EN/NL).

## 0.3.0
Backup and restore: encrypted full and incremental backups to SCP, FTPS and FTP with schedules and retention, restore
from the UI, from uploaded files and from the installer on a new server.

## 0.2.0
Consoles (UniFi Access API), vehicle list with presence per console, adopting existing Access users, CSV import
wizard with dry run and full sync, statistics, API keys and the first REST API.

## 0.1.0
Foundation: Debian 13 installer, admin layout in the RHIS house style (EN/NL, light/dark), local accounts with roles,
Microsoft Entra single sign-on, SMTP mail server, audit log, Info button with update check, in-app updates and
switching between production and test.
