# REST API voor het aanleveren van voertuigen (Lobster en andere systemen)

Deze handleiding is voor de leverancier van het systeem dat de bedrijfswagens aanlevert, zoals Lobster.
Ze beschrijft versie 1 van de API (`/api/v1`). English version: [api.md](api.md).

- Interactieve referentie: `http://<server>:8080/api/docs`, onderdeel **external API (v1)**
- Machineleesbare specificatie (OpenAPI 3.1): [openapi-v1.json](openapi-v1.json), ook live op `http://<server>:8080/api/openapi.json`

## Stappenplan voor de leverancier

1. Ontvang het serveradres en een API-key van de beheerder (zie hieronder).
2. Roep `GET /api/v1/status` aan om de verbinding en de key te testen.
3. Stuur één voertuig met `"dry_run": true` en controleer het antwoord.
4. Lever de voertuigen aan met `POST /api/v1/vehicles` en een `Idempotency-Key`-header.
5. Vraag `GET /api/v1/jobs/{id}` op tot `status` `done` of `failed` is, en leg het resultaat vast.

## Authenticatie

Een beheerder maakt een API-key aan onder **Beheer › API-keys**. De key begint met `lpr_` en wordt één keer
getoond. Stuur hem mee met elk verzoek:

```
Authorization: Bearer lpr_...
```

- Elke wijziging met een key wordt in het auditlog vastgelegd onder de naam van de key.
- Een key zonder **Verwijderen van voertuigen toestaan** kan toevoegen en bijwerken, maar geen voertuigen
  verwijderen (`mode: "full"` en `DELETE` worden geweigerd).
- Een key kan beperkt worden tot **toegestane adressen**: IP-adressen of netwerken (CIDR, bijvoorbeeld
  `203.0.113.10` of `10.20.0.0/16`). Verzoeken vanaf andere adressen krijgen `403 ip_not_allowed`. Geef de
  beheerder het publieke IP-adres (of de adressen) waarvandaan jullie systeem verbinding maakt.
- De applicatie luistert op poort 8080. Gaat het verkeer over internet, verbind dan alleen via HTTPS
  (reverse proxy) of een VPN; de beheerder geeft je het adres. De key is een wachtwoord: houd hem buiten
  logbestanden en broncode.

## Velden van een voertuig

| Veld | Verplicht | Betekenis |
| --- | --- | --- |
| `plate` | ja | Kenteken in elke notatie. Nederlandse kentekens krijgen de officiële notatie (`12bdf3` → `12-BDF-3`). |
| `department` | ja | Afdeling, bijvoorbeeld `Netwerktransport` (max. 100 tekens). Wordt de voornaam van de UniFi Access-gebruiker. |
| `location` | nee | Standplaats, bijvoorbeeld `Wognum` (max. 100 tekens). |
| `group_name` | nee | Gebruikersgroep in UniFi Access (max. 200 tekens). Standaard: afdeling + standplaats, bijvoorbeeld `Netwerktransport Wognum`. |
| `description` | nee | Vrije tekst, bijvoorbeeld merk en type. Wordt na 255 tekens afgekapt. Een lege waarde laat de bestaande omschrijving staan. |

In UniFi Access wordt elk voertuig een gebruiker met voornaam = afdeling, achternaam = kenteken, het kenteken als
credential, en lid van de groep. Ontbrekende groepen worden aangemaakt.

## Voertuigen aanleveren

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

| Veld | Standaard | Betekenis |
| --- | --- | --- |
| `vehicles` | | 1 tot 20.000 voertuigen. |
| `mode` | `upsert` | `upsert` voegt alleen toe en werkt bij. `full` verwijdert ook voertuigen van **dezelfde afdelingen** die niet meer in de lijst staan, uit de applicatie en van elke console. `full` vraagt een key die mag verwijderen. |
| `consoles` | alle | Lijst met consolenamen of id's om op te registreren. Weggelaten = alle actieve consoles; `[]` = alleen in de app opslaan. |
| `dry_run` | `false` | `true` geeft terug wat er zou veranderen, zonder iets te wijzigen. |

Antwoord `202 Accepted`:

```json
{ "job_id": 42, "status": "queued", "status_url": "/api/v1/jobs/42", "replayed": false }
```

Regels met een ongeldig kenteken, zonder afdeling, met een te lange waarde of met een dubbel kenteken worden
overgeslagen; de overige regels worden verwerkt. Met `dry_run` is het antwoord `200 OK` met een `summary`
(aantallen `new`, `changed`, `unchanged`, `invalid`), de lijst `remove` bij full, en de overgeslagen regels onder
`invalid` met hun `error` (`invalid_plate`, `missing_department`, `too_long`, `duplicate`).

### Idempotentie en opnieuw proberen

Stuur een `Idempotency-Key`-header met een unieke waarde per levering (bijvoorbeeld een UUID, max. 100 tekens).
Valt de verbinding weg en stuur je hetzelfde verzoek binnen 24 uur opnieuw met dezelfde waarde, dan start er geen
tweede taak: het antwoord is `200 OK` met de oorspronkelijke `job_id` en `"replayed": true`. Gebruik voor elke
nieuwe levering een nieuwe waarde.

Probeer opnieuw bij netwerkfouten en bij status `502`, `503` en `504`, met een oplopende pauze (bijvoorbeeld
10 s, 30 s, 2 min). Probeer `4xx`-antwoorden niet opnieuw zonder het verzoek aan te passen.

### Een taak volgen

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

- `status`: `queued` → `running` → `done` of `failed`. Wijzigingen op de consoles lopen één taak tegelijk, dus
  een taak kan even `queued` blijven als er al een import loopt.
- `processed`, `succeeded`, `failed`: één stap per voertuig per console.
- `done` met `failed > 0` betekent dat sommige stappen mislukt zijn (bijvoorbeeld een console die offline was);
  de `log` vertelt welke.
- Vraag de status elke 2 tot 5 seconden op. Een key ziet alleen zijn eigen taken.

De beheerder kan een mail krijgen met het importrapport, of alleen als er iets misging (**Beheer › Meldingen**).

## Overige aanroepen

| Aanroep | Doel |
| --- | --- |
| `GET /api/v1/status` | Verbindingstest: naam van de key, of hij mag verwijderen, versie van de applicatie, aantal actieve consoles |
| `GET /api/v1/vehicles` | Alle voertuigen met de consoles waarop ze aanwezig zijn. Optionele filters `?department=` en `?location=` |
| `GET /api/v1/vehicles/{plate}` | Eén voertuig, kenteken in elke notatie |
| `DELETE /api/v1/vehicles/{plate}` | Eén voertuig van alle consoles en uit de app verwijderen (key moet mogen verwijderen); antwoordt met een taak zoals `POST` |
| `GET /api/v1/consoles` | Actieve consoles (id, naam, standplaats) |
| `GET /api/v1/jobs/{id}` | Status en rapport van een taak die met deze key is gestart |

## Foutmeldingen

Fouten zijn JSON met een veld `detail`.

| Status | `detail` | Betekenis |
| --- | --- | --- |
| 400 | `unknown_console:<naam>` | Een console in `consoles` bestaat niet of is niet actief |
| 401 | `invalid_api_key` | Key ontbreekt, is onjuist of uitgeschakeld |
| 403 | `ip_not_allowed` | Het verzoek komt van een adres waarvandaan de key niet gebruikt mag worden |
| 403 | `delete_not_allowed` | De key mag geen voertuigen verwijderen |
| 404 | `not_found` | Voertuig of taak niet gevonden |
| 422 | (lijst) | De body voldoet niet aan het schema, bijvoorbeeld meer dan 20.000 voertuigen |

## Voorbeelden

```bash
# Verbindingstest
curl http://lpr.example.local:8080/api/v1/status -H "Authorization: Bearer lpr_..."

# Levering
curl -X POST http://lpr.example.local:8080/api/v1/vehicles \
  -H "Authorization: Bearer lpr_..." \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"vehicles":[{"plate":"12-BDF-3","department":"Netwerktransport","location":"Wognum"}]}'

# Status
curl http://lpr.example.local:8080/api/v1/jobs/42 -H "Authorization: Bearer lpr_..."
```

## Versies

Binnen `/api/v1` kunnen velden aan antwoorden worden toegevoegd; negeer velden die je niet kent. Wijzigingen die
niet terugwaarts compatibel zijn krijgen een nieuw pad (`/api/v2`), en `/api/v1` blijft tijdens een
overgangsperiode werken.
