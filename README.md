# UniFi Fabric License Plate Importer

Web application that registers company vehicles as UniFi Access users with linked license plates on every console in a UniFi Fabric, using the local UniFi Access API, so the gates open for them at every location.

Vehicles arrive in two ways:

- **CSV import** from the admin panel, with validation, preview and dry-run.
- **REST API**: external systems such as Lobster push vehicles to this application. API documentation (OpenAPI) is published so vendors can set up the integration themselves.

Imports are a full sync: vehicles missing from the source are removed from every console.

> Status: phase 1 (foundation). See [ROADMAP.md](ROADMAP.md).

## Installation (Debian 13)

On a fresh Debian 13 VM or physical server, as root:

```bash
curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/install.sh | bash
# or the test channel:
curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/install.sh | bash -s -- --branch test
```

The installer installs PostgreSQL, Python and Node.js, builds the app into `/opt/lpr-importer`, starts the
`lpr-importer` service on port 8080 and prints the first admin password. Running it again is safe.

| Path | Contents |
| --- | --- |
| `/etc/lpr-importer/lpr-importer.env` | Configuration (database, secret key, public URL) |
| `/var/lib/lpr-importer/` | Update status, update log, database snapshots made before each update |
| `journalctl -u lpr-importer -f` | Application log |

Forgot the admin password? `cd /opt/lpr-importer/backend && sudo -u lprimporter env $(cat /etc/lpr-importer/lpr-importer.env | xargs) ../.venv/bin/python -m app.cli reset-password admin`

## Updates and channels

The **Info** button (bottom of the menu) and **System & updates** show the installed version and check GitHub for new
releases. Updating, or switching between production (`main`) and test (`test`), runs `scripts/update.sh` through the
`lpr-importer-update` systemd unit: it makes a database snapshot, checks out the branch, rebuilds, runs migrations and
restarts. If the app does not come back, it rolls back to the previous commit.

Releases: bump `VERSION`, merge into `test`, try it, then merge `test` into `main`.

## Development

```bash
cd backend && python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements-dev.txt
LPR_DATABASE_URL=sqlite:///dev.db ../.venv/bin/alembic upgrade head
LPR_DATABASE_URL=sqlite:///dev.db ../.venv/bin/python -m app.cli create-admin
LPR_DATABASE_URL=sqlite:///dev.db ../.venv/bin/uvicorn app.main:app --port 8080 --reload
../.venv/bin/pytest            # backend tests
cd ../frontend && npm ci && npm run dev   # UI on http://localhost:5173, API proxied to 8080
```

The UI follows the RHIS house style (`frontend/public/brand`, tokens in `frontend/src/index.css`); the source of the
brand package is `brand/` in the rhis-website repository.

## Standard features

- Installer for Debian 13 (VM or physical server)
- Web interface on port 8080, modern UI with the admin menu on the left
- English by default, Dutch translation included
- Optional Microsoft Entra ID single sign-on
- Configurable SMTP mail server (STARTTLS/SSL, OAuth2)
- Full and incremental backups to FTP, FTPS and SCP, with restore from remote
- Info button with version, update check and in-app update
- Audit log of every change, with who made it (user or API key)
- Separate `main` (production) and `test` branches, switchable from the UI

## Branches

| Branch | Purpose |
| --- | --- |
| `main` | Production releases |
| `test` | Test releases, merged into `main` after approval |

---

## Nederlands

Webapplicatie die bedrijfswagens als UniFi Access-gebruikers met gekoppeld kenteken registreert op elke console, via de lokale UniFi Access API, zodat de slagbomen op alle locaties voor ze opengaan. Voertuigen komen binnen via CSV-import of via de REST API (bijvoorbeeld vanuit Lobster). Zie [ROADMAP.md](ROADMAP.md) voor de planning.
