# Manual – UniFi Fabric License Plate Importer

Version 1.0 · Nederlandse versie: [manual.nl.md](manual.nl.md)

This application registers company vehicles as UniFi Access users with a linked license plate on every UniFi
console, so the gates open for them at every location. Vehicles come from a CSV file, a scheduled import or an
external system such as Lobster through the REST API.

## Contents

1. [How it works](#1-how-it-works)
2. [Installation](#2-installation)
3. [Linking the consoles](#3-linking-the-consoles)
4. [Dashboard](#4-dashboard)
5. [Vehicles](#5-vehicles)
6. [Importing a CSV file](#6-importing-a-csv-file)
7. [Scheduled imports](#7-scheduled-imports)
8. [REST API for Lobster](#8-rest-api-for-lobster)
9. [Users, roles and single sign-on](#9-users-roles-and-single-sign-on)
10. [Mail server and notifications](#10-mail-server-and-notifications)
11. [Backup and restore](#11-backup-and-restore)
12. [Security](#12-security)
13. [Updates and channels](#13-updates-and-channels)
14. [Troubleshooting](#14-troubleshooting)
15. [Command line](#15-command-line)

## 1. How it works

- A **vehicle** is a license plate with a department, a location (standplaats), an optional group and a description.
- A **console** is a UniFi console running UniFi Access (4.2 or newer). The application talks to the local Access
  API of each console on port 12445 with an API token.
- Each vehicle becomes an Access user named by convention: first name = department, last name = plate, user group =
  department + location (for example `Netwerktransport Wognum`). The plate is linked to that user as a license plate
  credential, without dashes in capitals (`12BDF3`) unless you choose the official notation.
- The application reads every console regularly (hourly by default). The vehicle list and the dashboard show per
  console whether a plate is **present**, **missing** or present on the console but **not in the app**.
- Every change, by a person, an API key or the scheduler, is written to the **audit log**.

An import **adds and updates** by default. A **full sync** also removes the vehicles of the same departments that
the source no longer lists, from the app and from every console.

## 2. Installation

Requirements: a Debian 13 VM or physical server (2 CPU, 2 GB RAM, 10 GB disk is plenty) that can reach the consoles
on port 12445.

As root:

```bash
# one line; also works on a bare image without curl (such as the Proxmox LXC template):
apt-get update -qq && apt-get install -y -qq curl && curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/install.sh | bash
```

The installer opens dialogs and asks:

1. **Channel**: production (`main`, recommended) or test (`test`).
2. **Web access** on port 8080: plain HTTP, HTTPS with a self-signed certificate, or HTTPS with your own certificate
   (PEM files). Choose HTTPS when Lobster or other systems connect over the internet.
3. **Restore a backup** afterwards (for a server that replaces an old one, see [section 11](#11-backup-and-restore)).

A progress bar shows the step it is in (step 1 to 10: packages, system user, application, PostgreSQL,
configuration, HTTP/HTTPS, build, services, restore, admin account). At the end it shows the address and the first
admin password. Change that password after signing in (click your name at the top right, or **Users**).

Without a terminal, or with `--unattended`, the installer runs without dialogs. Options:

| Option | Meaning |
| --- | --- |
| `--branch main\|test` | Channel |
| `--https` | HTTPS on port 8080 with a self-signed certificate |
| `--cert FILE --key FILE` | HTTPS on port 8080 with your own certificate |
| `--http` | Plain HTTP on port 8080 |
| `--restore` | Restore a backup after installing |
| `--unattended` | No dialogs or questions |

Running the installer again is safe: configuration, data and accounts are kept. Use it to switch between HTTP and
HTTPS or to replace the certificate, for example `bash /opt/lpr-importer/install.sh --cert /root/new.pem --key /root/new.key`.

| Path | Contents |
| --- | --- |
| `/etc/lpr-importer/lpr-importer.env` | Configuration (database, secret key, address, HTTPS) |
| `/etc/lpr-importer/tls/` | HTTPS certificate and key |
| `/var/lib/lpr-importer/` | Update status and log, database snapshots before updates, backup and schedule state |
| `/var/log/lpr-importer-install.log` | Log of the last installer run |
| `journalctl -u lpr-importer -f` | Application log |

## 3. Linking the consoles

On every console, in UniFi Access: **Settings › General › Advanced › API Token**. Create a token with view and edit
rights for users and user groups.

In the application: **Consoles › Add console**. Enter a name, the location, the local IP address of the console and
the token. **Test** checks the connection and the Access version. **Read** loads the plates that are on the console
now.

Existing Access users with a plate that are not in the app yet are offered under **Vehicles › Review and adopt**, so
you do not have to enter them again.

Settings at the bottom of the Consoles page:

- **Plate notation** sent to Access: compact `12BDF3` (default) or official `12-BDF-3`.
- **Delete the Access user** when its only plate is removed.
- **Read the consoles automatically**: how often the plates of every console are read (hourly by default). Reading
  never changes anything on a console.

## 4. Dashboard

The dashboard is the start page.

- **Totals**: vehicles in the app, locations in order, plates missing on a console, plates on a console that are not
  in the app.
- **Status per location**: one card per console with a coloured status:
  - *In order*: reachable, read, all vehicles present, no failures in the last 24 hours.
  - *Attention*: vehicles missing, or a change failed in the last 24 hours.
  - *Problem*: the connection test or the last read failed. The last error is shown.
  - *Not read yet* / *Inactive*.
  The card shows the coverage, the time of the last read and the last change, and the number of changes and failures.
- **Recent syncs**: the last imports, registrations, removals and reads, with the source (CSV, REST API, scheduled
  import or automatic). Click a line for the full report.
- **Scheduled imports** with their next run and last result, and **System**: version, channel, last backup, single
  sign-on and mail server.

The dashboard refreshes itself every 30 seconds.

## 5. Vehicles

**Vehicles** lists every vehicle with one column per console: present, missing or not read yet. Search on plate,
filter on department, location, group or presence, and select vehicles to:

- **Assign** them to one or more consoles (for example a missing plate),
- **Remove** them from consoles (and optionally from the app),
- **Edit** department, location or group in bulk.

**Add vehicle** adds a single vehicle by hand.

## 6. Importing a CSV file

**Import** is a wizard in four steps:

1. **Upload** a CSV file (semicolon or comma, header row; Excel exports work).
2. **Map columns**: which column is the plate, department, location, group and description. Columns are recognised
   automatically (Dutch and English names); a fixed value can be entered for an empty or missing column. The mapping
   is remembered.
3. **Review and group**: per row new, changed, unchanged or invalid. Filter on location, exclude rows, change the
   group of a selection.
4. **Register**: choose the consoles and the mode (add and update, or full sync). The numbers per console come from
   the last read. Nothing changes before you start this step.

## 7. Scheduled imports

**Scheduled imports** fetches a CSV file on a schedule and imports it with the same rules as the wizard. Use it when a
system drops an export file somewhere, for example every morning.

**Add scheduled import**:

1. **Where is the file?** A web address (HTTPS, optionally with a username and password) or a file on an SCP/SFTP,
   FTPS or FTP server (folder and file name). For SCP you can sign in with the application's own SSH key (shown in the
   dialog). **Test and read columns** downloads the file and shows what an import would do now.
2. **Which column is what?** Choose the columns from the file, and fixed values for empty columns.
3. **Only part of the file** (optional): only rows of certain locations or departments.
4. **What to do**: all active consoles (new consoles are included automatically) or a selection; add and update, or
   full sync.
5. **When**: hourly, daily, weekly or monthly at a set time.

Safety rules for unattended runs:

- **Skip when the file has not changed** (on by default): the file is compared with the previous run.
- A file **without valid vehicles** never starts an import.
- A full sync that would remove **more vehicles than the limit** (default 25) stops without changing anything. The
  run is marked as failed and, when notifications are on, a mail is sent.

**Run now** imports straight away, also when the file did not change. The report icon opens the report of the last
run. Operators can run imports; only administrators can add, change or delete them.

A run that was missed because the server was off is made up for when the server is back within six hours.

## 8. REST API for Lobster

External systems deliver vehicles through the REST API (`/api/v1`) with an API key. The full guide for the
supplier is in [api.md](api.md) ([Nederlands](api.nl.md)); the interactive reference is at `/api/docs`.

Administrators manage the keys under **API keys**: create a key (shown once), allow or forbid removing vehicles, and
limit the key to the IP addresses or networks the supplier connects from. Each key may make 600 requests per minute
by default (see [Security](#12-security)).

## 9. Users, roles and single sign-on

| Role | May |
| --- | --- |
| Read-only | View the dashboard, vehicles, consoles and statistics |
| Operator | Also import, register and remove vehicles, read consoles, run scheduled imports, view the audit log |
| Administrator | Everything, including users, consoles, API keys, settings, backups and updates |

**Users** manages local accounts. Lowering a role, disabling an account or setting a new password signs that user
out everywhere.

**Single sign-on** (Microsoft Entra ID): create an app registration in Entra, add the redirect URI shown on the page
as a *Web* redirect URI, create a client secret, and under *Token configuration* add the **groups** claim (security
groups). Fill in the tenant ID, client ID and secret, and map Entra groups to the three roles. A user gets the
highest role of their groups; users in none of the groups are refused. With **Allow password sign-in** off, only
local administrators can still sign in with a password (emergency access).

## 10. Mail server and notifications

**Mail server**: your own SMTP server with STARTTLS or SSL/TLS, username and password, or Microsoft 365 with OAuth2
(client credentials). **Send test mail** checks the settings.

**Notifications** mails the recipients you enter:

- **Import report** after CSV imports, scheduled imports and API deliveries (always, only on problems, or never),
- **Failed sync** when registering or removing a plate on a console fails,
- **Available update** when a new version is published on the installed channel.

Backup results are mailed according to the setting on the Backup page.

## 11. Backup and restore

**Backup & restore** sends encrypted backups to one or more of your own servers over SCP (SSH), FTPS or FTP.

- A **full backup** holds all data of the application; an **incremental backup** only what changed since the
  previous backup on that location. Both have their own schedule. Old backups are removed after the number of full
  backups you keep.
- Every file is encrypted with AES-256-GCM with the **backup passphrase**. Store it in your password manager: a
  backup cannot be restored without it.
- For SCP, sign in with a password or (recommended) with the application's SSH key: add the public key shown on the
  page to `~/.ssh/authorized_keys` of the backup user. The server's host key is trusted on the first connection and
  checked after that.

**Restore** from the list of backups on a location, or upload `.lprbak` files. Restoring an incremental backup uses
its full backup and the incrementals in between. A copy of the current data is saved first in
`/var/lib/lpr-importer/backup/pre-restore/`. Nothing changes on the UniFi consoles.

**New server**: install with `--restore` (or choose *Restore* in the installer dialog). The installer asks for the
backup location and the passphrase. Passwords and tokens in the backup are re-encrypted with the new server's secret
key.

## 12. Security

**Security** (administrators):

- **Sessions**: maximum session length (12 hours) and sign-out after inactivity (60 minutes). 0 = no idle limit.
- **Rate limiting**: after 5 failed sign-ins a user name is locked for 15 minutes; an IP address after 20. The REST
  API allows 600 requests per minute per key; an address that sends more than 30 wrong keys in a minute is paused for
  a minute.
- **Server checks**: whether HTTPS is used, whether cookies are sent only over HTTPS, and whether the secret key is
  strong.
- **Signed-in sessions**: everyone who is signed in, with browser, IP address and last activity. **Sign out** ends a
  session immediately.

Every user can click their name at the top right to see **My sessions** and sign out other browsers. Changing your
password signs out your other sessions.

What is protected and how:

- Console tokens, SMTP, SSO and backup passwords, the backup passphrase and the SSH key are encrypted in the database
  with the server's secret key (`LPR_SECRET_KEY`). The application refuses to start on PostgreSQL without one.
- User passwords are stored as Argon2 hashes, API keys as SHA-256 hashes; neither can be read back.
- The web interface sends strict security headers (Content-Security-Policy, no framing, no MIME sniffing) and
  protects every change against cross-site requests.
- Use HTTPS when traffic leaves the internal network: run the installer with `--https` or `--cert/--key`. The
  installer then also sets secure cookies.

## 13. Updates and channels

The **Info** button (bottom of the menu) shows the version, channel and commit and checks GitHub for updates.
**System & updates** installs an update or switches between production (`main`) and test (`test`).

An update makes a database snapshot, downloads the branch, rebuilds, runs the database migrations and restarts. If
the application does not come back, the previous version is restored automatically. The last five snapshots are
kept in `/var/lib/lpr-importer/pre-update/`.

## 14. Troubleshooting

| Problem | What to do |
| --- | --- |
| Console shows *Problem* | Open **Consoles** and click **Test**. Check the IP address, port 12445 in the firewall, the token (Access settings) and the Access version (4.2+). |
| Vehicle *missing* on a console | Select it under **Vehicles** and click **Assign**. The report shows the reason when it fails. |
| Scheduled import *failed* | Read the message on the card and open the report. *too many removals*: check the export; raise the limit only if the removals are expected. |
| Lobster gets `401` | The key is wrong or disabled. `403 ip_not_allowed`: add Lobster's address to the key. `429`: too many requests, wait for `Retry-After`. |
| Locked out after failed sign-ins | Wait 15 minutes, or restart the service (`systemctl restart lpr-importer`) to clear the counters. |
| Admin password lost | See [Command line](#15-command-line): `reset-password`. |
| Browser warns about the certificate | Expected with a self-signed certificate: trust it once, or install your own with `--cert/--key`. |
| Update failed | **System & updates** shows the log; the previous version is restored. Full log: `/var/lib/lpr-importer/update.log`. |

## 15. Command line

Run as root on the server:

```bash
cd /opt/lpr-importer/backend
APP="sudo -u lprimporter env $(cat /etc/lpr-importer/lpr-importer.env | xargs) ../.venv/bin/python -m app.cli"
$APP reset-password admin        # new random password for a local account
$APP create-admin                # first admin account, when none exists
$APP backup --kind full          # backup to every enabled location now
$APP restore                     # restore from a location or files (asks for what is missing)
```

Service: `systemctl status|restart lpr-importer` · Log: `journalctl -u lpr-importer -f`.
