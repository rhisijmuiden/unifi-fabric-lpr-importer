# UniFi Fabric License Plate Importer

Web application that registers company vehicles as UniFi Access users with linked license plates on every console in a UniFi Fabric, using the local UniFi Access API, so the gates open for them at every location.

Vehicles arrive in two ways:

- **CSV import** from the admin panel, with validation, preview and dry-run.
- **REST API**: external systems such as Lobster push vehicles to this application. API documentation (OpenAPI) is published so vendors can set up the integration themselves.

Imports are a full sync: vehicles missing from the source are removed from every console.

> Status: planning. See [ROADMAP.md](ROADMAP.md).

## Standard features

- Installer for Debian 13 (VM or physical server)
- Web interface on port 8080, modern UI with the admin menu on the left
- English by default, Dutch translation included
- Optional Microsoft Entra ID single sign-on
- Configurable SMTP mail server (STARTTLS/SSL, OAuth2)
- Full and incremental backups to FTP, FTPS and SCP, with restore from remote
- Info button with version, update check and in-app update
- Separate `main` (production) and `test` branches, switchable from the UI

## Branches

| Branch | Purpose |
| --- | --- |
| `main` | Production releases |
| `test` | Test releases, merged into `main` after approval |

---

## Nederlands

Webapplicatie die bedrijfswagens als UniFi Access-gebruikers met gekoppeld kenteken registreert op elke console, via de lokale UniFi Access API, zodat de slagbomen op alle locaties voor ze opengaan. Voertuigen komen binnen via CSV-import of via de REST API (bijvoorbeeld vanuit Lobster). Zie [ROADMAP.md](ROADMAP.md) voor de planning.
