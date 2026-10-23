# Handleiding – UniFi Fabric License Plate Importer

Versie 1.0 · English version: [manual.md](manual.md)

Deze applicatie registreert bedrijfswagens als UniFi Access-gebruikers met een gekoppeld kenteken op elke UniFi
console, zodat de slagbomen op alle locaties voor ze opengaan. Voertuigen komen uit een CSV-bestand, een geplande
import of een extern systeem zoals Lobster via de REST API.

## Inhoud

1. [Hoe het werkt](#1-hoe-het-werkt)
2. [Installatie](#2-installatie)
3. [Consoles koppelen](#3-consoles-koppelen)
4. [Dashboard](#4-dashboard)
5. [Voertuigen](#5-voertuigen)
6. [Een CSV-bestand importeren](#6-een-csv-bestand-importeren)
7. [Geplande imports](#7-geplande-imports)
8. [REST API voor Lobster](#8-rest-api-voor-lobster)
9. [Gebruikers, rollen en single sign-on](#9-gebruikers-rollen-en-single-sign-on)
10. [Mailserver en meldingen](#10-mailserver-en-meldingen)
11. [Back-up en herstel](#11-back-up-en-herstel)
12. [Beveiliging](#12-beveiliging)
13. [Updates en kanalen](#13-updates-en-kanalen)
14. [Problemen oplossen](#14-problemen-oplossen)
15. [Opdrachtregel](#15-opdrachtregel)

## 1. Hoe het werkt

- Een **voertuig** is een kenteken met een afdeling, een standplaats, een optionele groep en een omschrijving.
- Een **console** is een UniFi console met UniFi Access (4.2 of nieuwer). De applicatie praat met de lokale Access
  API van elke console op poort 12445 met een API-token.
- Elk voertuig wordt een Access-gebruiker volgens de naamgeving: voornaam = afdeling, achternaam = kenteken,
  gebruikersgroep = afdeling + standplaats (bijvoorbeeld `Netwerktransport Wognum`). Het kenteken wordt als
  kentekencredential aan die gebruiker gekoppeld, zonder streepjes in hoofdletters (`12BDF3`), tenzij je de
  officiële notatie kiest.
- De applicatie leest elke console regelmatig in (standaard elk uur). De voertuigenlijst en het dashboard tonen per
  console of een kenteken **aanwezig** is, **ontbreekt**, of wel op de console staat maar **niet in de app**.
- Elke wijziging, door een persoon, een API-key of de planner, komt in het **auditlog**.

Een import **voegt standaard toe en werkt bij**. Een **volledige synchronisatie** verwijdert daarnaast de voertuigen
van dezelfde afdelingen die de bron niet meer noemt, uit de app en van elke console.

## 2. Installatie

Benodigd: een Debian 13 VM of fysieke server (2 CPU, 2 GB RAM, 10 GB schijf is ruim voldoende) die de consoles op
poort 12445 kan bereiken.

Als root:

```bash
# een minimale Debian 13 image (zoals de Proxmox LXC-template) heeft nog geen curl:
apt-get update && apt-get install -y curl
curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/install.sh | bash
```

De installer opent schermen en vraagt:

1. **Kanaal**: productie (`main`, aanbevolen) of test (`test`).
2. **Webtoegang** op poort 8080: gewone HTTP, HTTPS met een zelfondertekend certificaat, of HTTPS met een eigen
   certificaat (PEM-bestanden). Kies HTTPS als Lobster of andere systemen via internet verbinden.
3. Daarna een **back-up terugzetten** (voor een server die een oude vervangt, zie [hoofdstuk 11](#11-back-up-en-herstel)).

Een voortgangsbalk toont in welke stap de installer is (stap 1 tot 10: pakketten, systeemgebruiker, applicatie,
PostgreSQL, configuratie, HTTP/HTTPS, bouwen, services, herstel, beheerdersaccount). Aan het eind toont hij het adres
en het eerste beheerderswachtwoord. Wijzig dat wachtwoord na het inloggen.

Zonder terminal, of met `--unattended`, draait de installer zonder schermen. Opties:

| Optie | Betekenis |
| --- | --- |
| `--branch main\|test` | Kanaal |
| `--https` | HTTPS op poort 8080 met een zelfondertekend certificaat |
| `--cert BESTAND --key BESTAND` | HTTPS op poort 8080 met een eigen certificaat |
| `--http` | Gewone HTTP op poort 8080 |
| `--restore` | Na de installatie een back-up terugzetten |
| `--unattended` | Geen schermen of vragen |

De installer opnieuw draaien is veilig: configuratie, gegevens en accounts blijven behouden. Gebruik hem om te
wisselen tussen HTTP en HTTPS of om het certificaat te vervangen, bijvoorbeeld
`bash /opt/lpr-importer/install.sh --cert /root/nieuw.pem --key /root/nieuw.key`.

| Pad | Inhoud |
| --- | --- |
| `/etc/lpr-importer/lpr-importer.env` | Configuratie (database, geheime sleutel, adres, HTTPS) |
| `/etc/lpr-importer/tls/` | HTTPS-certificaat en sleutel |
| `/var/lib/lpr-importer/` | Updatestatus en -log, databasesnapshots voor updates, status van back-ups en planningen |
| `/var/log/lpr-importer-install.log` | Log van de laatste installatie |
| `journalctl -u lpr-importer -f` | Applicatielog |

## 3. Consoles koppelen

Op elke console, in UniFi Access: **Settings › General › Advanced › API Token**. Maak een token met lees- en
schrijfrechten voor gebruikers en gebruikersgroepen.

In de applicatie: **Consoles › Console toevoegen**. Vul een naam, de standplaats, het lokale IP-adres van de console
en het token in. **Testen** controleert de verbinding en de Access-versie. **Uitlezen** haalt de kentekens op die nu op
de console staan.

Bestaande Access-gebruikers met een kenteken die nog niet in de app staan, worden aangeboden onder **Voertuigen ›
Bekijken en overnemen**, zodat je ze niet opnieuw hoeft in te voeren.

Instellingen onderaan de pagina Consoles:

- **Kentekennotatie** richting Access: compact `12BDF3` (standaard) of officieel `12-BDF-3`.
- **Access-gebruiker verwijderen** als zijn enige kenteken wordt verwijderd.
- **Consoles automatisch uitlezen**: hoe vaak de kentekens van elke console worden uitgelezen (standaard elk uur).
  Uitlezen wijzigt nooit iets op een console.

## 4. Dashboard

Het dashboard is de startpagina.

- **Totalen**: voertuigen in de app, locaties in orde, kentekens die op een console ontbreken, kentekens op een
  console die niet in de app staan.
- **Status per locatie**: één kaart per console met een gekleurde status:
  - *In orde*: bereikbaar, uitgelezen, alle voertuigen aanwezig, geen fouten in de laatste 24 uur.
  - *Aandacht*: er ontbreken voertuigen, of een wijziging is in de laatste 24 uur mislukt.
  - *Probleem*: de verbindingstest of het laatste uitlezen is mislukt. De laatste fout staat erbij.
  - *Nog niet uitgelezen* / *Inactief*.
  De kaart toont de dekking, het moment van laatst uitlezen en de laatste wijziging, en het aantal wijzigingen en fouten.
- **Recente synchronisaties**: de laatste imports, registraties, verwijderingen en uitleesacties, met de bron (CSV,
  REST API, geplande import of automatisch). Klik op een regel voor het volledige verslag.
- **Geplande imports** met hun volgende keer en laatste resultaat, en **Systeem**: versie, kanaal, laatste back-up,
  single sign-on en mailserver.

Het dashboard ververst zichzelf elke 30 seconden.

## 5. Voertuigen

**Voertuigen** toont elk voertuig met één kolom per console: aanwezig, ontbreekt of nog niet uitgelezen. Zoek op
kenteken, filter op afdeling, standplaats, groep of aanwezigheid, en selecteer voertuigen om:

- ze **toe te wijzen** aan een of meer consoles (bijvoorbeeld een ontbrekend kenteken),
- ze van consoles te **verwijderen** (**Verwijderen van consoles**) (en eventueel uit de app),
- afdeling, standplaats of groep in één keer te **bewerken**.

**Voertuig toevoegen** voegt één voertuig met de hand toe.

## 6. Een CSV-bestand importeren

**Import** is een wizard in vier stappen:

1. **Uploaden** van een CSV-bestand (puntkomma of komma, met kopregel; Excel-exports werken).
2. **Kolommen koppelen**: welke kolom het kenteken, de afdeling, de standplaats, de groep en de omschrijving is.
   Kolommen worden automatisch herkend (Nederlandse en Engelse namen); voor een lege of ontbrekende kolom kun je een
   vaste waarde invullen. De koppeling wordt onthouden.
3. **Controleren en groeperen**: per regel nieuw, gewijzigd, ongewijzigd of ongeldig. Filter op standplaats, sluit
   regels uit, wijzig de groep van een selectie.
4. **Registreren**: kies de consoles en de modus (toevoegen en bijwerken, of volledige synchronisatie). De aantallen
   per console komen uit het laatste uitlezen. Er verandert niets voordat je deze stap start.

## 7. Geplande imports

**Geplande imports** haalt volgens een schema een CSV-bestand op en importeert het met dezelfde regels als de wizard.
Gebruik dit als een systeem ergens een exportbestand neerzet, bijvoorbeeld elke ochtend.

**Geplande import toevoegen**:

1. **Waar staat het bestand?** Een webadres (HTTPS, eventueel met gebruikersnaam en wachtwoord) of een bestand op een
   SCP/SFTP-, FTPS- of FTP-server (map en bestandsnaam). Voor SCP kun je inloggen met de eigen SSH-sleutel van de
   applicatie (staat in het venster). **Testen en kolommen lezen** downloadt het bestand en toont wat een import nu
   zou doen.
2. **Welke kolom is wat?** Kies de kolommen uit het bestand, en vaste waarden voor lege kolommen.
3. **Alleen een deel van het bestand** (optioneel): alleen regels van bepaalde standplaatsen of afdelingen.
4. **Wat moet er gebeuren**: alle actieve consoles (nieuwe consoles doen automatisch mee) of een selectie; toevoegen
   en bijwerken, of volledige synchronisatie.
5. **Wanneer**: elk uur, elke dag, elke week of elke maand op een vast tijdstip.

Veiligheidsregels voor onbewaakte imports:

- **Overslaan als het bestand niet is gewijzigd** (standaard aan): het bestand wordt vergeleken met de vorige keer.
- Een bestand **zonder geldige voertuigen** start nooit een import.
- Een volledige synchronisatie die **meer voertuigen dan de limiet** zou verwijderen (standaard 25) stopt zonder iets
  te wijzigen. De import krijgt de status mislukt en als meldingen aanstaan gaat er een mail uit.

**Nu uitvoeren** importeert direct, ook als het bestand niet is gewijzigd. Het verslagpictogram opent het verslag van
de laatste keer. Operators kunnen imports uitvoeren; alleen beheerders kunnen ze toevoegen, wijzigen of verwijderen.

Een import die is gemist omdat de server uit stond, wordt ingehaald als de server binnen zes uur terug is.

## 8. REST API voor Lobster

Externe systemen leveren voertuigen via de REST API (`/api/v1`) met een API-key. De volledige handleiding voor de
leverancier staat in [api.nl.md](api.nl.md) ([English](api.md)); de interactieve referentie staat op `/api/docs`.

Beheerders beheren de keys onder **API-keys**: een key aanmaken (één keer getoond), verwijderen van voertuigen
toestaan of niet, en de key beperken tot de IP-adressen of netwerken waarvandaan de leverancier verbindt. Elke key
mag standaard 600 verzoeken per minuut doen (zie [Beveiliging](#12-beveiliging)).

## 9. Gebruikers, rollen en single sign-on

| Rol | Mag |
| --- | --- |
| Alleen lezen | Dashboard, voertuigen, consoles en statistieken bekijken |
| Operator | Daarnaast importeren, voertuigen registreren en verwijderen, consoles uitlezen, geplande imports uitvoeren, auditlog bekijken |
| Beheerder | Alles, inclusief gebruikers, consoles, API-sleutels, instellingen, back-ups en updates |

**Gebruikers** beheert lokale accounts. Een lagere rol, een uitgeschakeld account of een nieuw wachtwoord logt die
gebruiker overal uit.

**Single sign-on** (Microsoft Entra ID): maak in Entra een app-registratie, voeg de redirect-URI van de pagina toe als
*Web*-redirect-URI, maak een client secret, en voeg onder *Token configuration* de claim **groups** (security groups)
toe. Vul tenant-ID, client-ID en secret in en koppel Entra-groepen aan de drie rollen. Een gebruiker krijgt de hoogste
rol van zijn groepen; gebruikers in geen van de groepen worden geweigerd. Met **Inloggen met wachtwoord toestaan** uit
kunnen alleen lokale beheerders nog met een wachtwoord inloggen (noodtoegang).

## 10. Mailserver en meldingen

**Mailserver**: je eigen SMTP-server met STARTTLS of SSL/TLS, gebruikersnaam en wachtwoord, of Microsoft 365 met
OAuth2 (client credentials). **Testmail versturen** controleert de instellingen.

**Meldingen** mailt de ontvangers die je invult:

- **Importrapport** na CSV-imports, geplande imports en leveringen via de API (altijd, alleen bij problemen, of nooit),
- **Mislukte synchronisatie** als registreren of verwijderen van een kenteken op een console mislukt,
- **Beschikbare update** als er een nieuwe versie op het geïnstalleerde kanaal staat.

Back-upresultaten worden gemaild volgens de instelling op de pagina Back-up.

## 11. Back-up en herstel

**Back-up & herstel** stuurt versleutelde back-ups naar een of meer van je eigen servers via SCP (SSH), FTPS of FTP.

- Een **volledige back-up** bevat alle gegevens van de applicatie; een **incrementele back-up** alleen wat sinds de
  vorige back-up op die locatie is gewijzigd. Beide hebben hun eigen schema. Oude back-ups worden verwijderd na het
  aantal volledige back-ups dat je bewaart.
- Elk bestand is versleuteld met AES-256-GCM met de **back-upwachtzin**. Bewaar die in je wachtwoordmanager: zonder
  wachtzin kan een back-up niet worden teruggezet.
- Voor SCP log je in met een wachtwoord of (aanbevolen) met de SSH-sleutel van de applicatie: zet de publieke sleutel
  van de pagina in `~/.ssh/authorized_keys` van de back-upgebruiker. De hostsleutel van de server wordt bij de eerste
  verbinding vertrouwd en daarna gecontroleerd.

**Terugzetten** vanuit de lijst met back-ups op een locatie, of door `.lprbak`-bestanden te uploaden. Een incrementele
back-up terugzetten gebruikt de bijbehorende volledige back-up en de incrementele back-ups daartussen. Eerst wordt een
kopie van de huidige gegevens bewaard in `/var/lib/lpr-importer/backup/pre-restore/`. Er verandert niets op de UniFi
consoles.

**Nieuwe server**: installeer met `--restore` (of kies *Terugzetten* in het installatiescherm). De installer vraagt
om de back-uplocatie en de wachtzin. Wachtwoorden en tokens in de back-up worden opnieuw versleuteld met de geheime
sleutel van de nieuwe server.

## 12. Beveiliging

**Beveiliging** (beheerders):

- **Sessies**: maximale sessieduur (12 uur) en uitloggen na inactiviteit (60 minuten). 0 = geen limiet.
- **Rate limiting**: na 5 mislukte inlogpogingen wordt een gebruikersnaam 15 minuten geblokkeerd; een IP-adres na 20.
  De REST API staat 600 verzoeken per minuut per key toe; een adres dat binnen een minuut meer dan 30 onjuiste keys
  stuurt, wordt een minuut gepauzeerd.
- **Servercontroles**: of HTTPS wordt gebruikt, of cookies alleen via HTTPS gaan, en of de geheime sleutel sterk is.
- **Ingelogde sessies**: iedereen die is ingelogd, met browser, IP-adres en laatste activiteit. **Uitloggen** beëindigt
  een sessie direct.

Elke gebruiker kan rechtsboven op zijn naam klikken voor **Mijn sessies** en andere browsers uitloggen. Je wachtwoord
wijzigen logt je andere sessies uit.

Wat is beschermd en hoe:

- Console-tokens, SMTP-, SSO- en back-upwachtwoorden, de back-upwachtzin en de SSH-sleutel staan versleuteld in de
  database met de geheime sleutel van de server (`LPR_SECRET_KEY`). Op PostgreSQL start de applicatie niet zonder.
- Gebruikerswachtwoorden worden als Argon2-hash bewaard, API-keys als SHA-256-hash; beide zijn niet terug te lezen.
- De webinterface stuurt strikte beveiligingsheaders mee (Content-Security-Policy, niet in frames, geen MIME-sniffing)
  en beschermt elke wijziging tegen cross-site verzoeken.
- Gebruik HTTPS als verkeer het interne netwerk verlaat: draai de installer met `--https` of `--cert/--key`. De
  installer zet dan ook veilige cookies aan.

## 13. Updates en kanalen

De knop **Info** (onderaan het menu) toont versie, kanaal en commit en controleert GitHub op updates.
**Systeem & updates** installeert een update of wisselt tussen productie (`main`) en test (`test`).

Een update maakt een databasesnapshot, haalt de branch op, bouwt opnieuw, voert de databasemigraties uit en herstart.
Komt de applicatie niet terug, dan wordt automatisch de vorige versie teruggezet. De laatste vijf snapshots staan in
`/var/lib/lpr-importer/pre-update/`.

## 14. Problemen oplossen

| Probleem | Wat te doen |
| --- | --- |
| Console toont *Probleem* | Open **Consoles** en klik **Testen**. Controleer het IP-adres, poort 12445 in de firewall, het token (Access-instellingen) en de Access-versie (4.2+). |
| Voertuig *ontbreekt* op een console | Selecteer het onder **Voertuigen** en klik **Toewijzen**. Het verslag toont de reden als het mislukt. |
| Geplande import *mislukt* | Lees de melding op de kaart en open het verslag. *te veel verwijderingen*: controleer de export; verhoog de limiet alleen als de verwijderingen kloppen. |
| Lobster krijgt `401` | De key is onjuist of uitgeschakeld. `403 ip_not_allowed`: voeg het adres van Lobster toe aan de key. `429`: te veel verzoeken, wacht `Retry-After`. |
| Geblokkeerd na mislukte inlogpogingen | Wacht 15 minuten, of herstart de service (`systemctl restart lpr-importer`) om de tellers te wissen. |
| Beheerderswachtwoord kwijt | Zie [Opdrachtregel](#15-opdrachtregel): `reset-password`. |
| Browser waarschuwt voor het certificaat | Normaal bij een zelfondertekend certificaat: vertrouw het één keer, of installeer een eigen certificaat met `--cert/--key`. |
| Update mislukt | **Systeem & updates** toont het log; de vorige versie is teruggezet. Volledig log: `/var/lib/lpr-importer/update.log`. |

## 15. Opdrachtregel

Als root op de server:

```bash
cd /opt/lpr-importer/backend
APP="sudo -u lprimporter env $(cat /etc/lpr-importer/lpr-importer.env | xargs) ../.venv/bin/python -m app.cli"
$APP reset-password admin        # nieuw willekeurig wachtwoord voor een lokaal account
$APP create-admin                # eerste beheerdersaccount, als er nog geen is
$APP backup --kind full          # nu een back-up naar elke actieve locatie
$APP restore                     # terugzetten vanaf een locatie of bestanden (vraagt wat ontbreekt)
```

Service: `systemctl status|restart lpr-importer` · Log: `journalctl -u lpr-importer -f`.
