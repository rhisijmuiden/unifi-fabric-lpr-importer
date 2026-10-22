# REST API voor het aanleveren van voertuigen (Lobster en andere systemen)

Deze handleiding is voor de leverancier van het systeem dat de bedrijfswagens aanlevert, zoals Lobster.
De interactieve referentie (OpenAPI) staat op `https://<server>:8080/api/docs`, onderdeel **external API (v1)**.

## Authenticatie

Een beheerder maakt een API-key aan onder **Beheer › API-keys**. De key begint met `lpr_` en wordt één keer
getoond. Stuur hem mee met elk verzoek:

```
Authorization: Bearer lpr_...
```

Elke wijziging met een key wordt in het auditlog vastgelegd onder de naam van de key. Een key zonder
**Verwijderen van voertuigen toestaan** kan toevoegen en bijwerken, maar geen voertuigen verwijderen.

## Velden van een voertuig

| Veld | Verplicht | Betekenis |
| --- | --- | --- |
| `plate` | ja | Kenteken. Nederlandse kentekens krijgen de officiële notatie (`12bdf3` → `12-BDF-3`). |
| `department` | ja | Afdeling, bijvoorbeeld `Netwerktransport`. Wordt de voornaam van de UniFi Access-gebruiker. |
| `location` | nee | Standplaats, bijvoorbeeld `Wognum`. |
| `group_name` | nee | Gebruikersgroep in UniFi Access. Standaard: afdeling + standplaats, bijvoorbeeld `Netwerktransport Wognum`. |
| `description` | nee | Vrije tekst, bijvoorbeeld merk en type. |

In UniFi Access wordt elk voertuig een gebruiker met voornaam = afdeling, achternaam = kenteken, het kenteken als
credential, en lid van de groep. Ontbrekende groepen worden aangemaakt.

## Voertuigen aanleveren

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

- `mode`: `upsert` (standaard) voegt alleen toe en werkt bij. `full` verwijdert daarnaast voertuigen van **dezelfde
  afdelingen** die niet meer in de lijst staan, uit de applicatie en van alle consoles. Voor `full` is een key nodig
  die mag verwijderen.
- `consoles`: optionele lijst met namen of id's van consoles. Weggelaten = alle actieve consoles; `[]` = alleen in
  de app opslaan.
- `dry_run`: `true` geeft terug wat er zou veranderen, zonder iets te wijzigen.

Antwoord `202 Accepted`:

```json
{ "job_id": 42, "status": "queued", "status_url": "/api/v1/jobs/42" }
```

De voertuigen worden op de achtergrond geregistreerd. Vraag de status op via de status-URL:

`GET /api/v1/jobs/42` → `status` is `queued`, `running`, `done` of `failed`, met de tellers `processed`,
`succeeded`, `failed` en een `log` met één regel per voertuig per console.

Regels met een ongeldig kenteken, zonder afdeling of met een dubbel kenteken worden overgeslagen; bij `dry_run`
staan ze onder `invalid`.

## Overige aanroepen

| Aanroep | Doel |
| --- | --- |
| `GET /api/v1/vehicles` | Alle voertuigen, met de consoles waarop ze aanwezig zijn |
| `DELETE /api/v1/vehicles/{plate}` | Eén voertuig van alle consoles en uit de app verwijderen (key moet mogen verwijderen) |
| `GET /api/v1/consoles` | Actieve consoles (id, naam, standplaats) |
| `GET /api/v1/jobs/{id}` | Status van een taak die met deze key is gestart |

## Foutmeldingen

| Status | `detail` | Betekenis |
| --- | --- | --- |
| 401 | `invalid_api_key` | Key ontbreekt, is onjuist of uitgeschakeld |
| 403 | `delete_not_allowed` | De key mag geen voertuigen verwijderen |
| 400 | `unknown_console:<naam>` | Een console in `consoles` bestaat niet of is inactief |
| 404 | `not_found` | Voertuig of taak niet gevonden |
| 422 | (lijst) | Het verzoek voldoet niet aan het schema |

## Voorbeeld

```bash
curl -X POST https://lpr.example.local:8080/api/v1/vehicles \
  -H "Authorization: Bearer lpr_..." \
  -H "Content-Type: application/json" \
  -d '{"vehicles":[{"plate":"12-BDF-3","department":"Netwerktransport","location":"Wognum"}]}'
```
