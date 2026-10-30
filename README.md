# Weles

[Polski](#polski) · [English](#english)

## Polski

Aplikacja do obsługi pakowania zamówień dla sprzedawców Allegro, uruchamiana na
własnym komputerze lub serwerze. Jeden serwis Docker zastępuje pracę z arkuszem
i drukarką: pobiera zamówienia z Allegro, grupuje je w listy kompletowania,
prowadzi przez pakowanie i pozwala pobrać etykietę przesyłki oraz połączony
plik PDF z dokumentem sprzedażowym i własnym dokumentem.

Bez SaaS i opłat za użytkownika — zamówienia pozostają na Twoim urządzeniu,
a aplikacja komunikuje się tylko z API Allegro.

> **Status: działająca wersja beta.** Pobieranie zamówień, tworzenie przesyłek
> i pobieranie etykiet potwierdzono w **środowisku sandbox** dla **Allegro One Box, DPD**
> (2026-10-04). **Tworzenie przesyłek i pobieranie etykiet InPost nadal wymaga testów.**
> Działanie w środowisku produkcyjnym i pozostałe metody dostawy nie zostały jeszcze
> zweryfikowane. Etykiety przesyłek w środowisku produkcyjnym kosztują prawdziwe pieniądze.
> Zgłoszenia błędów i pull requesty są mile widziane.

### Możliwości

- **Synchronizacja** — pobieranie oczekujących zamówień z Allegro, również z wielu stron wyników.
- **Listy kompletowania** — grupowanie wybranych zamówień, aby zebrać produkty podczas jednego przejścia przez magazyn.
- **Kolejka pakowania** — przenoszenie skompletowanych zamówień do pakowania oraz ustawianie wymiarów i wagi paczki.
- **Gabaryty paczkomatowe** — zamówienia do Paczkomatów InPost oferują wybór A/B/C
  zamiast ręcznego wpisywania wymiarów; przy zakupie etykiety odpowiednie wymiary trafiają do Allegro.
- **Etykiety przesyłek** — zakup i pobieranie etykiet z Allegro (InPost i pozostali przewoźnicy
  przez Allegro Shipment Management). Etykieta jest tworzona raz dla danego zamówienia,
  a kolejne próby wydruku korzystają z istniejącej przesyłki.
- **Numery nadania** — zapisywane przy zamówieniu i widoczne na karcie pakowania,
  aby sprawdzić numer przesyłki bez wychodzenia z aplikacji.
- **Dokumenty** — połączony plik PDF z dokumentem sprzedażowym i własnym dokumentem dla pakowanego zamówienia.
- **Archiwum** — oznaczanie zamówień jako gotowe i ich archiwizowanie.

Każdy zapis trafia do jednego pliku stanu JSON (`data/state.json`), zapisywanego
atomowo (plik tymczasowy + fsync + zmiana nazwy). Poprzednia wersja pozostaje
w `state.json.bak`. Uszkodzony plik jest odkładany do kwarantanny, a nie nadpisywany.
Rekordy, które nie przechodzą walidacji, są wydzielane, zamiast blokować całą kolejkę.

### Wymagania

- Docker z Compose
- Aplikacja deweloperska Allegro (`https://developer.allegro.pl`) z Client ID i Client Secret
- Uprawnienia aplikacji: `allegro:api:orders:read`, `allegro:api:shipments:read`
  i `allegro:api:shipments:write` (pobieranie zamówień, dostęp do przesyłek i etykiet oraz tworzenie przesyłek).

### Szybki start

```sh
git clone https://github.com/majorlupa/packing.git
cd packing
cp .env.example .env
chmod 600 .env
docker compose build packing
docker compose up -d
```

Otwórz <http://localhost:3001>.

Aplikacja domyślnie uruchamia się po polsku. Przełącznik **Polski / English**, dostępny
już podczas pierwszej konfiguracji, pozwala zmienić język interfejsu. Wybór jest
zapamiętywany w przeglądarce i obejmuje również komunikaty oraz dokumenty generowane
przez aplikację. Dane zamówień, treść własnego dokumentu i etykiety dostarczane przez
przewoźników nie są tłumaczone.

Przy pierwszym uruchomieniu aplikacja prowadzi przez pozostałe kroki:

1. Wpisz Client ID i Client Secret aplikacji Allegro. Zostaną zapisane w pliku `.env`
   na hoście i zastosowane od razu.
2. Włącz wymagane uprawnienia w aplikacji deweloperskiej Allegro, a następnie kliknij
   **Autoryzuj Allegro**, aby połączyć konto sprzedawcy (OAuth2, adres przekierowania
   `http://localhost:3001/api/orders/auth/callback` — zarejestruj go w aplikacji Allegro).
3. Konfiguracja generuje `PACKING_ACCESS_TOKEN`, wyświetla go tylko raz i zapisuje.
   Zachowaj ten token: przeglądarka poprosi o niego przy kolejnych wizytach.

Do testów w sandboxie zarejestruj aplikację i edytuj jej ustawienia w
[panelu aplikacji sandbox](https://apps.developer.allegro.pl.allegrosandbox.pl/)
i pozostaw `ALLEGRO_SANDBOX=true`. W uprawnieniach do przesyłek włącz
**Odczyt przesyłek, etykiet i protokołów** oraz **Zarządzanie przesyłkami**.
Jeżeli zmienisz uprawnienia po połączeniu konta, kliknij **Połącz ponownie Allegro**
i zatwierdź nowy zakres dostępu.

Jeżeli pobieranie zamówień działa, ale obsługa przesyłek zwraca
**403 — No access to the specified resource** (aplikacja pokazuje ten błąd jako HTTP 502),
sprawdź uprawnienia do przesyłek i połącz konto ponownie. To rozwiązało problem
z przesyłkami podczas weryfikacji w sandboxie. Zobacz
[dokumentację uprawnień do przesyłek Allegro](https://developer.allegro.pl/news/udostepnilismy-nowe-zasoby-do-tworzenia-i-zarzadzania-przesylkami-w-ramach-wysylam-z-allegro-BvGe1loe7tk).

Aby przetestować aplikację bez połączenia z Allegro lub tworzyć symulowane etykiety,
ustaw `PACKING_SHIPMENT_DRY_RUN=true`. Pozwala to przejść cały proces: pobieranie
realistycznych zamówień testowych, tworzenie list kompletowania, wybór gabarytu A/B/C
Paczkomatu InPost, tworzenie przesyłek, numery nadania i puste etykiety PDF — bez
aktywnego połączenia z Allegro. Nigdy nie włączaj tego trybu w środowisku produkcyjnym.

W trybie testowym widok oczekujących zamówień udostępnia też przycisk
**Wczytaj zamówienia testowe**, który dodaje trzy przykładowe zamówienia, aby można
było sprawdzić cały proces przy pustej kolejce. Przycisk jest dostępny tylko w tym
trybie; endpoint `POST /api/orders/seed-mock` poza nim zwraca 409. Zamówienia testowe
mają fikcyjne identyfikatory Allegro i nie można ich wysłać — nie powinny trafiać
do rzeczywistej kolejki, gdzie mogłyby wyglądać jak opłacone zamówienia.

### Własny dokument dla klienta

W **Ustawienia → Dokumenty** wybierz wgrany PDF lub szablon zaprojektowany w aplikacji.
Wgrany PDF pozostaje niezmienny. Szablon może zawierać logo PNG/JPEG (maks. 2 MB),
nagłówki, tekst, dane klienta i tabelę produktów. Bloki można przestawiać, a pola
osobowe wstawiać przyciskami: `{{buyer_name}}`, `{{buyer_address}}`, `{{order_number}}`,
`{{date}}`, `{{courier}}`, `{{pickup_point}}`, `{{tracking_number}}`.

Podgląd PDF wykorzystuje wybrane istniejące zamówienie i niezapisane zmiany; nie zapisuje
szablonu ani nie tworzy przesyłki. Numer nadania jest dostępny dopiero po jego zapisaniu
przy tworzeniu etykiety; brakujące dane opcjonalne pojawiają się jako „—”. Zapisz szablon
i wybór źródła przed drukowaniem podczas pakowania. W Pakowaniu jest jeden przycisk:
**Własny dokument**, gdy wybrane źródło jest dostępne, albo **Dokument** dla dokumentu
sprzedażowego. Drukowana jest tylko jedna wersja, bez łączenia obu dokumentów.
Dokument sprzedażowy pozostaje bez zmian.

Przełączenie źródła zachowuje zarówno szablon, jak i wgrany plik. Ustawienia są trwałe;
pierwsza wersja udostępnia jeden szablon, a struktura danych pozostawia miejsce na kolejne.
Obsługa wielu kont Allegro nie jest jeszcze dostępna. Wgrany PDF musi być czytelny,
niezaszyfrowany i mieć co najmniej jedną stronę (maks. 20 MB).

### Konfiguracja

Wszystkie ustawienia znajdują się w `.env`; wymagane są tylko dane dostępowe Allegro
i token dostępu. Ustawienia opcjonalne opisano w [`.env.example`](.env.example)
(tryb sandbox, adres przekierowania, dodatkowe źródła CORS, tryb testowy).

Serwis Compose montuje katalog `./data` ze stanem aplikacji oraz plik `.env` z hosta
wewnątrz kontenera. Dzięki temu plik pozostaje źródłem konfiguracji po restartach
i aktualizacjach. Zachowaj uprawnienia `0600` i nie dodawaj go do kontroli wersji.
Port aplikacji jest dostępny wyłącznie na localhost.

### Kopia zapasowa i przywracanie

`./data` zawiera zamówienia, listy kompletowania, archiwum, ustawienia i szablony
dokumentów (`state.json` i kopie), tokeny OAuth Allegro (`allegro_token.json`)
oraz wgrany PDF (`custom_doc.pdf`). Z katalogu projektu:

```sh
docker compose stop packing
tar -czf data-backup.tar.gz data   # albo skopiuj cały katalog ./data
docker compose up -d
```

Przywracanie (zachowaj obecny katalog pod nieużywaną nazwą):

```sh
docker compose stop packing
mv data data.before-restore
tar -xzf data-backup.tar.gz
sudo chown -R 1000:1000 data
docker compose up -d
```

Kontener działa jako UID/GID `1000:1000`; katalog musi być dla niego zapisywalny.
Osobno zachowaj `.env` (konfiguracja i token dostępu), z właścicielem `1000:1000`
i uprawnieniami `0600`. Chroń obie kopie: zawierają dane klientów i sekrety.

### Aktualizacje

Najpierw wykonaj kopię `data` i `.env`. Przy czystym drzewie roboczym:

```sh
previous=$(git rev-parse HEAD)   # zachowaj ten identyfikator do wycofania aktualizacji
git pull
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:3001/health
```

Jeśli kontrola nie przejdzie, sprawdź `docker compose logs packing`.
Aby wycofać: `git switch --detach "$previous"`, następnie ponownie
`docker compose build --pull` i `docker compose up -d`; sprawdź `/health`.
Jeśli zmienił się format danych, przed uruchomieniem starej wersji przywróć kopię
według instrukcji powyżej. Powrót na gałąź: `git switch -`.

### Reverse proxy i TLS

Compose udostępnia `127.0.0.1:3001:3001`. Poniższe przykłady zakładają proxy na
tym samym hoście. Zastąp domenę i ścieżki certyfikatów; skieruj DNS na serwer
i udostępnij porty 80/443. Ustaw `ALLEGRO_REDIRECT_URI` w `.env` na
`https://packing.example.com/api/orders/auth/callback`, zarejestruj ten sam adres
w Allegro i odtwórz kontener (`docker compose up -d --force-recreate packing`).

nginx (certyfikat TLS należy uzyskać osobno; 25 MB pozwala wgrać PDF 20 MB):

```nginx
server {
    listen 80;
    server_name packing.example.com;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name packing.example.com;
    ssl_certificate /etc/letsencrypt/live/packing.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/packing.example.com/privkey.pem;
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Caddy automatycznie uzyskuje TLS, przekierowuje HTTP na HTTPS, zachowuje `Host`
i ustawia `X-Forwarded-For`, `X-Forwarded-Proto` oraz `X-Forwarded-Host`:

```caddyfile
packing.example.com {
    reverse_proxy 127.0.0.1:3001
}
```

### Rozwój i testy

```sh
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
PACKING_ENV_FILE=.env python -m pytest backend/tests -q      # bez wywołań Allegro
node --test frontend/tests/*.test.cjs                       # testy interfejsu i języków
```

Katalogi tłumaczeń interfejsu znajdują się w `frontend/static/app.js`, a komunikaty
backendu i wybór języka w `backend/localization.py`. Każde żądanie do API aplikacji
wysyła `Accept-Language: pl` lub `en`, również podczas pobierania dokumentów
i rozpoczynania autoryzacji OAuth. Dane operatora i zamówień oraz tekst otrzymany
od przewoźników należy pozostawić poza katalogami tłumaczeń. Zmiana języka aktualizuje
tekst bez przebudowywania formularzy i kolejek.

Backend udostępnia statyczny frontend i API na porcie 3001. Stan aplikacji i tokeny
Allegro są zapisywane w `data/` i zachowywane po restartach kontenera.

### Sterowanie przez MCP (LLM)

Katalog `mcp_server/` zawiera serwer MCP, który wykonuje te same czynności co
interfejs, wywołując istniejące endpointy API: pobieranie zamówień, kolejki i statusy,
listy kompletowania, gabaryty A/B/C, etykiety i dokumenty, ustawienia. Działa jako
osobny proces (domyślnie stdio) i nie zmienia zachowania aplikacji.

```sh
python3 -m venv .venv
.venv/bin/pip install -r mcp_server/requirements.txt
export PACKING_ACCESS_TOKEN='<token z .env>'
.venv/bin/python -m mcp_server serve                       # serwer MCP dla klienta LLM
.venv/bin/python -m mcp_server sync-loop --interval 300    # synchronizacja bez LLM
```

`print_label` tworzy przesyłkę (najwyżej raz na zamówienie) i drukuje etykietę przez
CUPS (`lp`, kolejka z `PACKING_PRINTER` albo domyślna). Konfiguracja, pełna lista
narzędzi z endpointami, przykład systemd/cron i ustawienia drukowania:
[docs/mcp-server.md](docs/mcp-server.md).

### Licencja

Projekt jest udostępniany na [licencji MIT](LICENSE). Można go używać, modyfikować
i rozpowszechniać, również komercyjnie, pod warunkiem zachowania informacji
o prawach autorskich i treści licencji.

### Zastrzeżenia

To niezależne, nieukończone narzędzie, które nie jest powiązane z Allegro ani przez
nie zatwierdzone. Twórz kopie zapasowe `data/`. Do symulowanych przesyłek używaj
`PACKING_SHIPMENT_DRY_RUN=true`, ale wyłącz ten tryb przy sprawdzaniu rzeczywistych
etykiet w sandboxie. Sprawdź etykietę przed przekazaniem paczki kurierowi.

---

## English

Self-hosted order packing desk for Allegro sellers. One Docker service replaces
the spreadsheet-and-printer routine: orders are synced from Allegro, batched into
picking lists, packed, and finished with a real shipment label and either a
sales document or a custom customer PDF.

No SaaS, no per-seat fees — your orders stay on your machine and only talk to Allegro's API.

> **Status: working beta.** Allegro order sync, shipment creation and label download
> have been confirmed working in the **sandbox** for **Allegro One Box, DPD**
> (2026-10-04). **InPost shipment creation and labels still need testing.** Production
> use and other delivery methods are not yet verified. Shipping labels in production
> cost real money. Issues and pull requests welcome.

### What it does

- **Sync** pending orders from Allegro (pagination included).
- **Picking lists** – group selected orders into one walk through the warehouse.
- **Packing queue** – move picked orders into packing, set parcel dimensions and weight.
- **Locker sizes** – InPost Paczkomat orders offer gabaryt A/B/C instead of manual
  dimensions; the matching locker dimensions are sent to Allegro when the label is bought.
- **Shipment labels** – buy and download an Allegro label (InPost and other carriers via
  Allegro Shipment Management). Labels are created once per order and reused afterwards.
- **Tracking numbers** – stored per order and shown on the packing card, so you can
  follow a parcel without leaving the app.
- **Documents** – combined sales/custom document PDF for a packed order.
- **Archive** – mark orders done and archive them.

Every write goes to a single JSON state file (`data/state.json`) written atomically
(temp file + fsync + rename), with the previous generation kept as `state.json.bak`.
A corrupted file is quarantined, not overwritten, and records that fail validation are
set aside instead of taking the whole queue down.

### Requirements

- Docker with Compose
- Allegro developer app (`https://developer.allegro.pl`) with Client ID and Client Secret
- App permissions: `allegro:api:orders:read`, `allegro:api:shipments:read` and
  `allegro:api:shipments:write` (order sync, shipment/label access and shipment creation).

### Quick start

```sh
git clone https://github.com/majorlupa/packing.git
cd packing
cp .env.example .env
chmod 600 .env
docker compose build packing
docker compose up -d
```

Open <http://localhost:3001>.

The application starts in Polish. Use the **Polski / English** selector, available
from onboarding onward, to change the interface language. The choice is remembered
in your browser and also applies to application-generated documents and messages.
Order data, custom document content, and carrier-provided shipment labels are not
translated.

First run walks you through the rest:

1. Enter the Allegro Client ID and Client Secret. They are written to `.env` on the host
   and applied immediately.
2. Enable the required permissions in your Allegro developer app, then use
   **Autoryzuj Allegro** to connect the seller account (OAuth2, redirect URI
   `http://localhost:3001/api/orders/auth/callback` – register it in your Allegro app).
3. Setup generates a `PACKING_ACCESS_TOKEN`, shows it once, and saves it. Keep it: your
   browser asks for it on later visits.

For sandbox testing, register and edit your app in
[sandbox application management](https://apps.developer.allegro.pl.allegrosandbox.pl/)
and keep `ALLEGRO_SANDBOX=true`. Under shipping permissions, enable **Odczyt przesyłek,
etykiet i protokołów** and **Zarządzanie przesyłkami**. If you change permissions after
connecting, click **Połącz ponownie Allegro** and approve the updated access.

If order sync works but shipping returns **403 — No access to the specified resource**
(shown as HTTP 502 by the app), check those shipping permissions and reconnect.
This resolved the sandbox shipping failure during verification. See
[Allegro's shipping permission documentation](https://developer.allegro.pl/news/udostepnilismy-nowe-zasoby-do-tworzenia-i-zarzadzania-przesylkami-w-ramach-wysylam-z-allegro-BvGe1loe7tk).

To test without an Allegro connection or create simulated labels,
use `PACKING_SHIPMENT_DRY_RUN=true` to exercise the entire application flow (order sync with realistic
mock orders, picking lists, Paczkomat InPost gabaryt A/B/C selection, shipment creation, tracking numbers,
and blank PDF labels) without needing a live Allegro connection. Never enable dry run in production.

In dry run the pending view also offers **Wczytaj zamówienia testowe**, which plants three
sample orders so the workflow can be walked through with an empty queue. That button and
its endpoint `POST /api/orders/seed-mock` exist only in dry run: the API answers 409
otherwise, because those orders carry invented Allegro ids that cannot be shipped and
would sit in a real queue looking like paid ones.

### Custom customer document

In **Settings → Documents**, choose an uploaded PDF or a template designed in the app.
Uploaded PDFs stay unchanged. Templates support a PNG/JPEG logo (max. 2 MB), headings,
text, customer details and a product table. Reorder blocks and insert dynamic fields
using buttons: `{{buyer_name}}`, `{{buyer_address}}`, `{{order_number}}`, `{{date}}`,
`{{courier}}`, `{{pickup_point}}` and `{{tracking_number}}`.

PDF preview uses a selected existing order and unsaved edits without saving the template
or creating a shipment. Tracking is available only once label creation has saved it;
missing optional values appear as “—”. Save the template and source choice before
printing while packing. Packing shows one button: **Custom document** when the selected
source is available, otherwise **Document** for the sales document. It prints only
that document, never both combined. The sales document remains unchanged.

Switching sources preserves both the template and uploaded file. Settings survive
restarts. The first version exposes one template but stores a collection for future
expansion; multiple Allegro accounts are not supported yet. Uploaded PDFs must be
readable, unencrypted and contain at least one page (max. 20 MB).

### Configuration

Everything lives in `.env`; the only required keys are the Allegro credentials and the
access token. See [`.env.example`](.env.example) for the optional ones
(sandbox toggle, redirect URI, extra CORS origins, dry run).

The Compose service mounts `./data` for state and the host `.env` inside the container,
so the file stays the single source of truth across restarts and updates. Keep it mode
`0600` and out of version control. The web port is bound to localhost only.

### Backup & restore

`./data` holds orders, picking lists, archives, settings and document templates
(`state.json` and backups), Allegro OAuth tokens (`allegro_token.json`), and the
uploaded PDF (`custom_doc.pdf`). From the project directory:

```sh
docker compose stop packing
tar -czf data-backup.tar.gz data   # or copy the entire ./data directory
docker compose up -d
```

Restore (preserve the current directory under an unused name):

```sh
docker compose stop packing
mv data data.before-restore
tar -xzf data-backup.tar.gz
sudo chown -R 1000:1000 data
docker compose up -d
```

The container runs as UID/GID `1000:1000`; the directory must be writable by it.
Back up `.env` separately (configuration and access token), keeping ownership
`1000:1000` and mode `0600`. Protect both backups: they contain customer data and secrets.

### Upgrading

Back up `data` and `.env` first. With a clean working tree:

```sh
previous=$(git rev-parse HEAD)   # retain this revision for rollback
git pull
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:3001/health
```

If the check fails, inspect `docker compose logs packing`.
To roll back: `git switch --detach "$previous"`, then rerun
`docker compose build --pull` and `docker compose up -d`; check `/health` again.
If the data format changed, restore the backup as above before starting the old
version. Return to your branch with `git switch -`.

### Running behind a reverse proxy

Compose binds `127.0.0.1:3001:3001`. These examples assume a proxy on the same host.
Replace the domain and certificate paths; point DNS to the server and expose
ports 80/443. Set `ALLEGRO_REDIRECT_URI` in `.env` to
`https://packing.example.com/api/orders/auth/callback`, register the same URL
with Allegro, and recreate the container (`docker compose up -d --force-recreate packing`).

nginx (obtain a TLS certificate separately; 25 MB accommodates a 20 MB PDF upload):

```nginx
server {
    listen 80;
    server_name packing.example.com;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name packing.example.com;
    ssl_certificate /etc/letsencrypt/live/packing.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/packing.example.com/privkey.pem;
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Caddy automatically obtains TLS, redirects HTTP to HTTPS, preserves `Host`,
and sets `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host`:

```caddyfile
packing.example.com {
    reverse_proxy 127.0.0.1:3001
}
```

### Development

```sh
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
PACKING_ENV_FILE=.env python -m pytest backend/tests -q      # never calls Allegro
node --test frontend/tests/*.test.cjs                       # UI and language regressions
```

The UI catalogs are in `frontend/static/app.js`; backend messages and locale
negotiation are in `backend/localization.py`. Every application API request sends
`Accept-Language: pl` or `en`, including document requests and OAuth initiation.
Keep operator/order data and upstream carrier text outside the translation catalogs.
Language switching updates text in place rather than rebuilding forms or queues.

The backend serves the static frontend and API on port 3001. State and Allegro
tokens are persisted in `data/` across container restarts.

### Product filtering, inbound sync, and printer-free testing

#### Filter orders by product

MCP `list_orders(product="LEGO", status="pending")` matches a case-insensitive
substring in any line item's name, SKU (Allegro `offer.external.id`), or offer ID.
It combines with the existing status, courier, and buyer/address search filters.
The backend also exposes `GET /api/orders/?product=LEGO` (normal API bearer token
required). Omitting `product` leaves the UI and existing clients unchanged.
MCP `queue_counts` still describes the whole queue, not just matching orders.

For a batch, pass the returned local order IDs to `create_picking_list`, then
call `start_packing` with its list ID. Preview the `list_orders` result before
making those state changes. No batch mutation happens when listing orders.
Older orders gain missing SKU/offer metadata on their next sync when their line
item names and quantities still match; existing item data is not overwritten.

#### Inbound order-sync webhook

Set `PACKING_WEBHOOK_SECRET` in `.env` to a separate, randomly generated secret
(at least 32 characters recommended), then recreate the backend container:

```sh
docker compose up -d --force-recreate packing
# Supply the secret securely in the caller's environment, not in the URL.
curl --fail-with-body -X POST http://localhost:3001/api/webhooks/sync \
  -H "Authorization: Bearer ${PACKING_WEBHOOK_SECRET}"
```

This endpoint requires **only the dedicated webhook bearer secret**, not the UI/API
access token. Comparison is constant-time. An unset/empty secret disables it
(HTTP 503); missing or incorrect authentication returns HTTP 401. Keep it distinct
from `PACKING_ACCESS_TOKEN` so the external caller cannot access the other APIs.
The endpoint ignores the request body and triggers only an order sync; it does
not accept arbitrary commands, create shipments, or change packing status.
It waits for completion and returns `{"added": 0, "updated": 0, "total": 0}` with
actual counts. Allegro authorization/upstream errors use the same responses as
`POST /api/orders/sync`. Repeated calls deduplicate stored orders by Allegro ID.

Keep the default localhost binding for local callers. For remote services, use
an authenticated TLS reverse proxy or private tunnel; do not expose plain HTTP
or place the secret in query strings or logs. Apply rate limits at the proxy.

#### Five-minute sync in Docker

The optional `packing-sync` Compose service runs the existing headless loop,
without an LLM or browser. It waits for the backend health check, syncs immediately,
then waits `PACKING_SYNC_INTERVAL` seconds (default 300) after each attempt.
Failures are logged and retried at the next interval.

```sh
# First complete Allegro authorization and ensure .env has PACKING_ACCESS_TOKEN.
docker compose --profile sync up -d --build
docker compose logs -f packing-sync
# Stop automatic sync while leaving the UI running:
docker compose stop packing-sync
```

Set `PACKING_SYNC_INTERVAL=600` in `.env` for ten-minute intervals. The worker
uses `http://packing:3001` over the Compose network and the normal access token;
it needs no public port, webhook secret, state volume, or printer. If onboarding
or token rotation changed `.env`, recreate the worker to reload its environment:
`docker compose --profile sync up -d --force-recreate packing-sync`.

#### Print PDFs without a physical printer

MCP printing supports a virtual file destination. Set these variables in the
**MCP process environment** (it does not automatically load `.env`):

```sh
export PACKING_PRINT_DIR="$PWD/data/virtual-prints"
export PACKING_LABEL_DIR="$PWD/data/downloads"
python -m mcp_server serve
```

Both `print_label` and `print_document` now validate and save PDFs without needing
CUPS or invoking `lp`. Each invocation writes one uniquely named, owner-only PDF
to `PACKING_PRINT_DIR`, even when multiple copies are requested. Results contain
`printer: "file"`, `job_id: null`, `print_dry_run: true`, and the saved `print_path`;
`path` remains the separately downloaded source PDF. An invalid/unwritable output
directory fails preflight before any label booking. Files contain customer data:
protect the directory and remove old PDFs according to your retention policy.
Unset `PACKING_PRINT_DIR` to resume normal CUPS printing.

**Print dry-run is not shipment dry-run.** `print_label` can still buy a real
shipment if none exists. For safe end-to-end tests also set
`PACKING_SHIPMENT_DRY_RUN=true` on the **backend** and recreate it. Alternatively,
use `print_document` or `download_label`; `create_if_missing=false` on `print_label`
refuses to buy a missing shipment.

To test actual CUPS queueing instead, install `cups-client` and `printer-driver-cups-pdf`
(on Debian/Ubuntu), configure the PDF queue, find its name with `lpstat -p`, and
set `PACKING_PRINTER=PDF` (or its actual name). Leave `PACKING_PRINT_DIR` unset.
The CUPS PDF printer's destination/permissions are configured in the host's
`/etc/cups/cups-pdf.conf`; check its output directory after a job.

For a real printer later, configure a queue on host CUPS or a network CUPS server.
The bundled backend image does **not** install `lp`; for MCP printing in Docker,
use a derived image with `cups-client`, run the MCP process there, and either:

- Bind-mount `/run/cups/cups.sock:/run/cups/cups.sock` and set
  `CUPS_SERVER=/run/cups/cups.sock`; allow container UID 1000 to access the socket.
- Set `CUPS_SERVER=printer-host:631` for a reachable network CUPS server with the
  desired queue configured, then set `PACKING_PRINTER` to that queue's name.

Keep CUPS restricted to trusted clients. A raw IPP/network printer must first be
configured as a CUPS queue; `PACKING_PRINTER` is a queue name, not a device URI.
Browser print dialogs remain unchanged and use the browser machine's printers.

### MCP control (LLM)

`mcp_server/` holds an MCP server that performs the same actions as the UI by
calling the existing API endpoints: order sync, queues and statuses, picking lists,
locker sizes A/B/C, labels and documents, settings. It runs as a separate process
(stdio by default) and does not change how the app behaves.

```sh
python3 -m venv .venv
.venv/bin/pip install -r mcp_server/requirements.txt
export PACKING_ACCESS_TOKEN='<token from .env>'
.venv/bin/python -m mcp_server serve                       # MCP server for an LLM client
.venv/bin/python -m mcp_server sync-loop --interval 300    # sync without an LLM
```

`print_label` creates the shipment (at most once per order) and prints the label
through CUPS (`lp`, the `PACKING_PRINTER` queue or the default). Setup, the full tool
list with routes, a systemd/cron example and printing notes:
[docs/mcp-server.md](docs/mcp-server.md).

### License

Licensed under the [MIT License](LICENSE). Free to use, modify and distribute,
including commercially, provided the copyright and license notices are retained.

### Disclaimer

This is an independent, unfinished tool, not affiliated with or endorsed by Allegro.
Back up `data/`, use `PACKING_SHIPMENT_DRY_RUN=true` for simulated shipments, and
leave it disabled when verifying actual sandbox labels. Verify a label before
handing a parcel to the courier.
