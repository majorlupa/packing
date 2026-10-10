"""Polish/English localization for application-owned text.

The UI sends ``Accept-Language: pl`` or ``en`` on every application API call.
Only those two languages are negotiated; anything absent, unsupported or
malformed falls back to Polish (the default). The negotiated language lives in a
``ContextVar``, which is per-task, so concurrent requests can never leak their
language into each other — never use a module-level global for this.

Messages belong here, not inline in routes: text that a carrier or Allegro sent
is upstream data and must stay verbatim, while everything the application itself
writes is looked up by key and translated. ``t()`` is safe to call with an
explicit ``lang`` (used where no request scope exists, e.g. the OAuth callback
that must remember the language chosen at authorization start).
"""
from contextlib import contextmanager
from contextvars import ContextVar

DEFAULT_LANGUAGE = "pl"
SUPPORTED_LANGUAGES = ("pl", "en")

# Bound the work a hostile/silly header can cause; far above any real browser value.
MAX_HEADER_LENGTH = 8192

current_language: ContextVar[str] = ContextVar("packing_language", default=DEFAULT_LANGUAGE)

MESSAGES: dict[str, dict[str, str]] = {
    # --- shared ---
    "common.allegro_unreachable": {
        "pl": "Brak łączności z Allegro: {error}",
        "en": "Cannot reach Allegro: {error}",
    },
    "error.order_not_found": {
        "pl": "Nie znaleziono zamówienia.",
        "en": "Order not found.",
    },
    "error.picking_list_not_found": {
        "pl": "Nie znaleziono listy zbiorczej.",
        "en": "Picking list not found.",
    },
    # --- API access ---
    "auth.required": {
        "pl": "Wymagane uwierzytelnienie.",
        "en": "Authentication required.",
    },
    "auth.token_not_configured": {
        "pl": "Zmienna PACKING_ACCESS_TOKEN musi być ustawiona i mieć co najmniej 32 znaki.",
        "en": "PACKING_ACCESS_TOKEN must be configured with at least 32 characters.",
    },
    # --- queue / picking / packing ---
    "picking.default_name": {
        "pl": "Lista #{number}",
        "en": "List #{number}",
    },
    "orders.bad_order_id": {
        "pl": "Nie znaleziono zamówienia {order_id}.",
        "en": "Order {order_id} not found.",
    },
    "parcel.locker_only": {
        "pl": "Gabaryt A/B/C dotyczy tylko Paczkomat InPost.",
        "en": "Sizes A/B/C apply only to InPost parcel lockers.",
    },
    "parcel.shipment_exists": {
        "pl": "Przesyłka już istnieje — nie można zmienić gabarytu.",
        "en": "A shipment already exists — the size cannot be changed.",
    },
    # --- orders sync / test data ---
    "orders.seed_mock_disabled": {
        "pl": "Zamówienia testowe są dostępne tylko przy PACKING_SHIPMENT_DRY_RUN=1. "
              "Nie włączaj tego trybu na produkcji.",
        "en": "Sample orders are available only with PACKING_SHIPMENT_DRY_RUN=1. "
              "Never enable this mode in production.",
    },
    "orders.incomplete_sync": {
        "pl": "Niepełna synchronizacja: przekroczono limit {limit} zamówień. "
              "Nie zapisano wyników tej synchronizacji.",
        "en": "Incomplete sync: the limit of {limit} orders was exceeded. "
              "No results from this sync were saved.",
    },
    "label.select_size": {
        "pl": "Wybierz gabaryt paczki (A, B lub C) dla Paczkomatu InPost.",
        "en": "Choose a parcel size (A, B or C) for the InPost parcel locker.",
    },
    # --- printing / documents ---
    "print.pdf_required": {
        "pl": "Wymagany plik PDF.",
        "en": "A PDF file is required.",
    },
    "print.file_too_large": {
        "pl": "Plik jest za duży (limit 20 MB).",
        "en": "The file is too large (20 MB limit).",
    },
    "print.not_a_pdf": {
        "pl": "To nie jest plik PDF.",
        "en": "This is not a PDF file.",
    },
    "print.custom_doc_missing": {
        "pl": "Brak wgranego dokumentu.",
        "en": "No document has been uploaded.",
    },
    # --- sales document scaffolding ---
    "doc.title": {"pl": "Dokument sprzedażowy", "en": "Sales document"},
    "doc.products": {"pl": "Zamówione produkty", "en": "Ordered products"},
    "doc.product": {"pl": "Produkt", "en": "Product"},
    "doc.quantity": {"pl": "Ilość", "en": "Quantity"},
    "doc.unit_price": {"pl": "Cena jedn.", "en": "Unit price"},
    "doc.value": {"pl": "Wartość", "en": "Value"},
    "doc.total": {"pl": "Razem", "en": "Total"},
    "doc.buyer": {"pl": "Kupujący", "en": "Buyer"},
    "doc.address": {"pl": "Adres", "en": "Address"},
    "doc.courier": {"pl": "Kurier", "en": "Courier"},
    "doc.pickup_point": {"pl": "Punkt odbioru", "en": "Pickup point"},
    "doc.order_number": {"pl": "Nr zamówienia", "en": "Order number"},
    # --- setup ---
    "setup.invalid_credentials": {
        "pl": "Podaj poprawny Client ID i Client Secret (bez spacji i nowych linii).",
        "en": "Enter a valid Client ID and Client Secret (no spaces or newlines).",
    },
    "setup.invalid_credentials_bounded": {
        "pl": "Podaj poprawny Client ID i Client Secret "
              "(bez spacji i nowych linii, maksymalnie 4096 znaków).",
        "en": "Enter a valid Client ID and Client Secret "
              "(no spaces or newlines, at most 4096 characters).",
    },
    "setup.already_configured": {
        "pl": "Allegro jest już skonfigurowane.",
        "en": "Allegro is already configured.",
    },
    "setup.wrong_origin": {
        "pl": "Otwórz konfigurację w aplikacji Weles i spróbuj ponownie.",
        "en": "Open the configuration inside the Weles app and try again.",
    },
    "setup.localhost_only": {
        "pl": "Pierwszą konfigurację otwórz pod adresem localhost.",
        "en": "Open the first-run setup on the localhost address.",
    },
    "setup.save_failed": {
        "pl": "Nie udało się zapisać .env. Sprawdź uprawnienia pliku i montowanie w Dockerze, "
              "a następnie spróbuj ponownie.",
        "en": "Could not save .env. Check the file permissions and the Docker mount, "
              "then try again.",
    },
    # --- OAuth ---
    "oauth.invalid_state": {
        "pl": "Nieprawidłowy lub wygasły stan autoryzacji.",
        "en": "Invalid or expired authorization state.",
    },
    "oauth.rejected": {
        "pl": "Allegro odrzuciło autoryzację: {error}",
        "en": "Allegro rejected the authorization: {error}",
    },
    "oauth.missing_code": {
        "pl": "Brak parametru 'code' w callbacku Allegro.",
        "en": "Missing 'code' parameter in the Allegro callback.",
    },
    "oauth.callback_title": {
        "pl": "Autoryzacja Allegro",
        "en": "Allegro authorization",
    },
    "oauth.callback_back": {
        "pl": "Wróć do aplikacji Weles",
        "en": "Go back to the Weles app",
    },
    # --- state file ---
    "store.state_not_object": {
        "pl": "{path} nie zawiera obiektu JSON.",
        "en": "{path} does not contain a JSON object.",
    },
    "store.orders_collection": {
        "pl": "nie jest obiektem",
        "en": "is not an object",
    },
    "store.problem_missing_file": {
        "pl": "brak pliku",
        "en": "file missing",
    },
    "store.unreadable_and_no_backup": {
        "pl": "Nie można odczytać {path} ({problem}) ani kopii zapasowej {backup} ({exc}). "
              "Pliki nie zostały nadpisane — przywróć stan ręcznie lub popraw pliki "
              "i zrestartuj kontener.",
        "en": "Cannot read {path} ({problem}) nor the backup {backup} ({exc}). "
              "The files were not overwritten — restore the state manually or fix the files "
              "and restart the container.",
    },
    "store.unreadable_no_backup": {
        "pl": "Nie można odczytać {path} ({exc}). Plik NIE został nadpisany — przywróć go "
              "ręcznie z kopii zapasowej lub popraw i zrestartuj kontener.",
        "en": "Cannot read {path} ({exc}). The file was NOT overwritten — restore it from the "
              "backup or fix it and restart the container.",
    },
    "store.recovered_from_backup": {
        "pl": "Brak/czytelnego state.json nie było — odtworzono z kopii zapasowej.",
        "en": "There was no readable state.json — restored from the backup.",
    },
    "store.corrupt_recovered": {
        "pl": "state.json był uszkodzony — odtworzono z kopii zapasowej ({name}).",
        "en": "state.json was corrupted — restored from the backup ({name}).",
    },
    "store.quarantined": {
        "pl": "{count} rekord(ów) pominięto — dane nie przechodzą walidacji.",
        "en": "{count} record(s) skipped — the data does not pass validation.",
    },
    # --- Allegro client (wrapping, never replacing, upstream text) ---
    "allegro.what.order_list": {"pl": "lista zamówień", "en": "order list"},
    "allegro.what.code_exchange": {"pl": "wymiana kodu", "en": "code exchange"},
    "allegro.what.token_refresh": {"pl": "odświeżenie tokenu", "en": "token refresh"},
    "allegro.what.shipment_status": {"pl": "status przesyłki", "en": "shipment status"},
    "allegro.what.shipment_create": {"pl": "utworzenie przesyłki", "en": "shipment creation"},
    "allegro.what.shipment_details": {"pl": "szczegóły przesyłki", "en": "shipment details"},
    "allegro.what.delivery_proposals": {"pl": "propozycje wysyłki", "en": "delivery proposals"},
    "allegro.invalid_data": {
        "pl": "Allegro zwróciło nieprawidłowe dane ({what}).",
        "en": "Allegro returned invalid data ({what}).",
    },
    # App-owned wrapper around a failed Allegro API call. {what} is a translated
    # operation description (or a verbatim technical identifier such as
    # "checkout-forms"); {status} and {detail} (raw upstream text) stay verbatim.
    "allegro.api_error": {
        "pl": "Błąd Allegro ({what}, HTTP {status}): {detail}",
        "en": "Allegro {what} {status}: {detail}",
    },
    "allegro.op.refresh_token": {"pl": "odświeżenie tokenu", "en": "refresh token"},
    "allegro.op.token_exchange": {"pl": "wymiana tokenu", "en": "token exchange"},
    "allegro.op.create_shipment": {"pl": "utworzenie przesyłki", "en": "create shipment"},
    "allegro.op.shipment_status": {"pl": "status przesyłki", "en": "shipment status"},
    "allegro.op.label": {"pl": "pobranie etykiety", "en": "label API"},
    "allegro.session_expired": {
        "pl": "Sesja Allegro wygasła. Kliknij 'Autoryzuj Allegro'.",
        "en": "The Allegro session has expired. Click 'Connect Allegro'.",
    },
    "allegro.not_authorized": {
        "pl": "Allegro nie jest autoryzowane. Kliknij 'Autoryzuj Allegro'.",
        "en": "Allegro is not authorized. Click 'Connect Allegro'.",
    },
    "allegro.delivery_proposals_failed": {
        "pl": "Nie udało się pobrać danych wysyłki z Allegro ({status}). {detail}",
        "en": "Could not fetch shipping data from Allegro ({status}). {detail}",
    },
    "allegro.no_suggested_input": {
        "pl": "Allegro nie zwróciło proponowanych danych wysyłki.",
        "en": "Allegro returned no proposed shipping data.",
    },
    "allegro.no_sender": {
        "pl": "Brak danych nadawcy w Allegro. Dodaj domyślny adres w książce adresowej "
              "Wysyłam z Allegro, a następnie spróbuj ponownie.",
        "en": "No sender data in Allegro. Add a default address in the 'Ship with Allegro' "
              "address book and try again.",
    },
    "allegro.no_receiver": {
        "pl": "Allegro nie zwróciło danych odbiorcy z adresem e-mail zamówienia.",
        "en": "Allegro returned no recipient data with the order's e-mail address.",
    },
    "allegro.no_command_id": {
        "pl": "Brak commandId w odpowiedzi Allegro.",
        "en": "No commandId in the Allegro response.",
    },
    "allegro.no_shipment_id": {
        "pl": "Allegro nie zwróciło identyfikatora utworzonej przesyłki.",
        "en": "Allegro returned no identifier for the created shipment.",
    },
    "allegro.shipment_creation_failed": {
        "pl": "Nie udało się utworzyć przesyłki w Allegro: {detail}",
        "en": "Creating the shipment in Allegro failed: {detail}",
    },
    "allegro.shipment_timeout": {
        "pl": "Przekroczono czas oczekiwania na utworzenie przesyłki.",
        "en": "Timed out waiting for the shipment to be created.",
    },
    "allegro.shipment_hint": {
        "pl": "Sprawdź ustawienia Wysyłam z Allegro i uprawnienia aplikacji do przesyłek.",
        "en": "Check the 'Ship with Allegro' settings and the app's shipment permissions.",
    },
    "allegro.no_label_yet": {
        "pl": "Allegro nie ma jeszcze etykiety dla tej przesyłki.",
        "en": "Allegro does not have a label for this shipment yet.",
    },
    "allegro.label_not_pdf": {
        "pl": "Allegro zwróciło etykietę w formacie innym niż PDF. Istniejącą etykietę ZPL "
              "pobierz w Wysyłam z Allegro; nowe etykiety w aplikacji są PDF.",
        "en": "Allegro returned a label in a format other than PDF. Download the existing ZPL "
              "label in 'Ship with Allegro'; new labels in this app are PDF.",
    },
    # --- dry-run artefacts (never produced on a production instance) ---
    "label.dry_run_title": {"pl": "DRY RUN — testowa etykieta", "en": "DRY RUN — test label"},
}

# Split of "d.m.yyyy" (Polish) and "dd/mm/yyyy" (English) for the sales document.
# English matches the frontend locale (en-GB), which renders zero-padded day/month/year.
DATE_FORMATS = {"pl": "%-d.%-m.%Y", "en": "%d/%m/%Y"}


def normalize_language(language: str | None) -> str | None:
    """Return a supported language code for a tag, or None when unsupported."""
    if not language:
        return None
    base = language.strip().lower().replace("_", "-").split("-", 1)[0]
    return base if base in SUPPORTED_LANGUAGES else None


def negotiate_language(header: str | None, default: str = DEFAULT_LANGUAGE) -> str:
    """Pick pl/en from an ``Accept-Language`` header, honouring q values.

    Only ``pl`` and ``en`` are ever returned. A missing, empty, unsupported or
    malformed header yields ``default`` (Polish). Entries with an invalid or zero
    q value are ignored rather than guessed at.
    """
    fallback = default if default in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    if not header:
        return fallback

    best: tuple[float, int, str] | None = None
    for index, part in enumerate(str(header)[:MAX_HEADER_LENGTH].split(",")):
        bits = part.split(";")
        language = normalize_language(bits[0])
        if language is None:
            continue
        quality = 1.0
        for parameter in bits[1:]:
            key, _, value = parameter.partition("=")
            if key.strip().lower() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = -1.0  # malformed q: ignore this entry
                break
        if not 0 < quality <= 1:
            continue
        # Strictly greater keeps the earlier entry on a tie, so the browser's
        # own order (and Polish over English) decides equal-quality cases.
        if best is None or quality > best[0]:
            best = (quality, index, language)

    return best[2] if best is not None else fallback


def t(key: str, lang: str | None = None, **params: object) -> str:
    """Look up an application message, formatted with ``params``.

    ``lang`` overrides the request-scoped language (used where no request scope
    exists). An unknown key returns the key itself, so a missing translation is
    visible instead of silently blank; a key without an English entry falls back
    to Polish.
    """
    language = normalize_language(lang) or current_language.get()
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(language) or entry.get(DEFAULT_LANGUAGE)
    if template is None:
        return key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template


@contextmanager
def language_scope(language: str | None):
    """Set the language for the current context (thread/task) and restore it."""
    token = current_language.set(normalize_language(language) or DEFAULT_LANGUAGE)
    try:
        yield
    finally:
        current_language.reset(token)


def date_format(lang: str | None = None) -> str:
    """The sales-document date pattern for the current (or given) language."""
    language = normalize_language(lang) or current_language.get()
    return DATE_FORMATS.get(language, DATE_FORMATS[DEFAULT_LANGUAGE])
