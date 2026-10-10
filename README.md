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

### Konfiguracja

Wszystkie ustawienia znajdują się w `.env`; wymagane są tylko dane dostępowe Allegro
i token dostępu. Ustawienia opcjonalne opisano w [`.env.example`](.env.example)
(tryb sandbox, adres przekierowania, dodatkowe źródła CORS, tryb testowy).

Serwis Compose montuje katalog `./data` ze stanem aplikacji oraz plik `.env` z hosta
wewnątrz kontenera. Dzięki temu plik pozostaje źródłem konfiguracji po restartach
i aktualizacjach. Zachowaj uprawnienia `0600` i nie dodawaj go do kontroli wersji.
Port aplikacji jest dostępny wyłącznie na localhost.

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
picking lists, packed, and finished with a real shipment label and a combined
sales/custom document PDF.

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

### Configuration

Everything lives in `.env`; the only required keys are the Allegro credentials and the
access token. See [`.env.example`](.env.example) for the optional ones
(sandbox toggle, redirect URI, extra CORS origins, dry run).

The Compose service mounts `./data` for state and the host `.env` inside the container,
so the file stays the single source of truth across restarts and updates. Keep it mode
`0600` and out of version control. The web port is bound to localhost only.

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

### License

Licensed under the [MIT License](LICENSE). Free to use, modify and distribute,
including commercially, provided the copyright and license notices are retained.

### Disclaimer

This is an independent, unfinished tool, not affiliated with or endorsed by Allegro.
Back up `data/`, use `PACKING_SHIPMENT_DRY_RUN=true` for simulated shipments, and
leave it disabled when verifying actual sandbox labels. Verify a label before
handing a parcel to the courier.
