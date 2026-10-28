const API = '/api';
const ACCESS_TOKEN_STORAGE_KEY = 'weles.accessToken';
let accessToken = readStoredAccessToken();
let accessTokenPrompt = null;
let appReady = false;

function readStoredAccessToken() {
  try {
    return sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

function setAccessToken(token) {
  accessToken = token;
  try {
    if (token) sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
    else sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    // Authentication still works when browser storage is unavailable.
  }
}

// No logout UI exists yet; use this helper to discard operator credentials.
function clearAccessToken() {
  setAccessToken('');
}

// ---- i18n catalog ----
// Every app-owned string lives here. Keys are flat and grouped by area. A value
// is either a string (with {placeholders}) or a plural object keyed by
// Intl.PluralRules categories (pl: one/few/many, en: one/other). Both languages
// must define the same keys; a missing entry falls back to Polish and the
// catalog-parity test turns red.
//
// Carrier names, product names and any other value that comes from Allegro or an
// external API are NEVER listed here: they pass through untouched. Only strings
// the application itself owns are translated.
const DEFAULT_LANGUAGE = 'pl';
const SUPPORTED_LANGUAGES = ['pl', 'en'];
const LANGUAGE_STORAGE_KEY = 'weles.lang';
const LOCALES = { pl: 'pl-PL', en: 'en-GB' };

const MESSAGES = {
  pl: {
    'nav.queues': 'Kolejki',
    'nav.pending': 'Oczekujące',
    'nav.picking': 'Kompletowanie',
    'nav.packing': 'Pakowanie',
    'nav.done': 'Gotowe',
    'nav.sync': 'Pobierz zamówienia',
    'nav.authorizeAllegro': 'Autoryzuj Allegro',
    'nav.reconnectAllegro': 'Połącz ponownie Allegro',
    'nav.endDay': 'Zakończ dzień',
    'nav.settings': 'Ustawienia',
    'nav.language': 'Język',

    'common.save': 'Zapisz',
    'common.cancel': 'Anuluj',
    'common.delete': 'Usuń',
    'common.revertTitle': 'Cofnij do oczekujących',
    'common.copyId': 'Kopiuj ID',
    'common.errorPrefix': 'Błąd',
    'common.requestFailed': 'Nie udało się wykonać żądania. Spróbuj ponownie.',
    'allegro.not_authorized': 'Połącz ponownie Allegro, aby kontynuować.',
    'common.allegro_unreachable': 'Nie można połączyć się z Allegro. Spróbuj ponownie później.',
    'allegro.request_failed': 'Żądanie do Allegro nie powiodło się. Spróbuj ponownie.',

    'unit.order': { one: 'zamówienie', few: 'zamówienia', many: 'zamówień' },
    'unit.product': { one: 'produkt', few: 'produkty', many: 'produktów' },
    'unit.transaction': { one: 'transakcja', few: 'transakcje', many: 'transakcji' },

    'category.locker': 'Paczkomat InPost',
    'category.other': 'Inny',

    'banner.problem': 'Problem ze stanem aplikacji.',
    'banner.quarantined': {
      one: '{n} rekord pominięto — dane nie przechodzą walidacji.',
      few: '{n} rekordy pominięto — dane nie przechodzą walidacji.',
      many: '{n} rekordów pominięto — dane nie przechodzą walidacji.',
    },

    'token.prompt': 'Podaj PACKING_ACCESS_TOKEN z pliku .env:',
    'token.required': 'Token dostępu jest wymagany.',

    'print.popupBlocked': 'Przeglądarka blokuje okno wydruku. Zezwól na wyskakujące okna i spróbuj ponownie.',

    'pending.title': 'Oczekujące zamówienia',
    'pending.createList': 'Utwórz listę kompletowania',
    'pending.selectHint': 'Zaznacz produkty',
    'pending.emptyLead': 'Brak oczekujących zamówień. Kliknij "Pobierz zamówienia"',
    'pending.emptyOr': 'lub',
    'pending.seedSample': 'Wczytaj zamówienia testowe',
    'pending.transactionCount': { one: '{n} transakcja', few: '{n} transakcje', many: '{n} transakcji' },
    'err.createList': 'Nie udało się utworzyć listy',
    'err.seedSample': 'Nie udało się wczytać zamówień testowych',

    'picking.title': 'Kompletowanie',
    'picking.empty': 'Brak aktywnych list kompletowania.',
    'picking.orderCount': { one: '{n} zamówienie', few: '{n} zamówienia', many: '{n} zamówień' },
    'picking.rename': 'Zmień nazwę',
    'picking.print': 'Drukuj listę',
    'picking.start': 'Pakuj →',
    'picking.printTitle': 'Lista: {name}',
    'picking.printProduct': 'Produkt',
    'picking.printQty': 'Ilość',
    'err.rename': 'Nie udało się zmienić nazwy',
    'err.revertList': 'Nie udało się cofnąć listy',
    'err.startPacking': 'Nie udało się przenieść do pakowania',

    'packing.title': 'Pakowanie',
    'packing.empty': 'Brak zamówień do pakowania. Przesuń listę kompletowania do pakowania.',
    'packing.prev': 'Poprzednie',
    'packing.next': 'Następne',
    'packing.trackingLabel': 'Nr przesyłki:',
    'packing.lockerLegend': 'Paczkomat InPost — gabaryt paczki',
    'packing.sizeA': 'Mała (8×38×64 cm)',
    'packing.sizeB': 'Średnia (19×38×64 cm)',
    'packing.sizeC': 'Duża (41×38×64 cm)',
    'packing.dims': 'Wymiary (cm)',
    'packing.weight': 'Waga (kg)',
    'packing.selectSizeNote': 'Wybierz gabaryt paczki (A, B lub C), aby utworzyć etykietę Paczkomat InPost.',
    'packing.savingSize': 'Zapisywanie gabarytu…',
    'packing.saveError': 'Nie udało się zapisać gabarytu: {detail}',
    'packing.labelLocker': 'Etykieta Paczkomat',
    'packing.labelCourier': 'Etykieta kurierska',
    'packing.invoice': 'Dokument',
    'packing.customDoc': 'Własny dokument',
    'packing.done': 'GOTOWE',
    'packing.generatingLabel': 'Generowanie etykiety…',
    'packing.doneConfirm': 'Etykieta nie wydrukowana — czy na pewno chcesz oznaczyć jako gotowe?',
    'err.revertOrder': 'Nie udało się cofnąć zamówienia',
    'err.copyId': 'Nie udało się skopiować ID',
    'err.label': 'Nie udało się pobrać etykiety',
    'err.document': 'Nie udało się wygenerować dokumentu',
    'err.done': 'Nie udało się oznaczyć jako gotowe',

    'done.title': 'Gotowe ({n})',
    'done.empty': 'Brak ukończonych zamówień.',
    'done.labelCreated': 'Etykieta utworzona',
    'done.labelMissing': '— brak etykiety —',
    'done.undo': 'Cofnij',

    'settings.title': 'Ustawienia',
    'settings.documentEditor': 'Edytor dokumentu A4',
    'settings.documentEditorDesc': 'Zaprojektuj dokument PDF, wstaw pola dynamiczne i importuj lub eksportuj szablony JSON.',
    'settings.openDocumentEditor': 'Przejdź do edytora dokumentu',
    'doc.blockPanel': 'Bloki i pola dynamiczne',
    'settings.tabDocuments': 'Dokumenty',
    'settings.tabShipping': 'Wysyłka',
    'settings.tabArchive': 'Archiwum',
    'settings.docsIntro': 'Zaznacz pola które mają pojawiać się na wydruku.',
    'inv.buyerName': 'Nazwa kupującego',
    'inv.buyerAddress': 'Adres kupującego',
    'inv.items': 'Lista produktów',
    'inv.price': 'Cena za sztukę',
    'inv.courier': 'Kurier',
    'inv.pickupPoint': 'Punkt odbioru (paczkomat)',
    'inv.allegroId': 'Numer zamówienia Allegro',
    'inv.freeTextLabel': 'Tekst własny (maks. 160 znaków)',
    'inv.freeTextPlaceholder': 'np. Dziękujemy za zakup!',
    'settings.customDocDesc': 'Własny dokument PDF — drukowany przyciskiem "Własny dokument" podczas pakowania.',
    'settings.docUploaded': 'Dokument wgrany',
    'settings.docNone': 'Brak dokumentu',
    'settings.docReplace': 'Zastąp plik',
    'settings.docChoose': 'Wybierz plik PDF',
    'settings.docUploadedOk': 'Wgrano pomyślnie',
    'settings.saved': 'Zapisano',
    'settings.error': 'Błąd',
    'err.docDelete': 'Nie udało się usunąć dokumentu',

    'doc.source': 'Źródło dokumentu',
    'doc.sourceUpload': 'Wgrany plik PDF',
    'doc.sourceTemplate': 'Zaprojektowany szablon',
    'doc.templateName': 'Nazwa szablonu',
    'doc.blockHeading': 'Nagłówek',
    'doc.blockType': 'Rodzaj bloku',
    'doc.blockText': 'Tekst',
    'doc.blockPlaceholder': 'Pole dynamiczne',
    'doc.blockLine': 'Linia',
    'doc.bold': 'Pogrubienie',
    'doc.templates': 'Szablony',
    'doc.duplicate': 'Duplikuj',
    'doc.export': 'Eksportuj bieżący',
    'doc.exportAll': 'Eksportuj wszystkie',
    'doc.import': 'Importuj JSON',
    'doc.importConflict': 'Konflikt szablonów przy imporcie',
    'doc.importRename': 'Zmień nazwę przy konflikcie',
    'doc.importOverwrite': 'Nadpisz przy konflikcie',
    'doc.importInvalid': 'Nieprawidłowy plik JSON.',
    'doc.imported': 'Zaimportowano szablony: {count}',
    'doc.deleteTemplate': 'Usuń szablon',
    'doc.sample': 'Dane przykładowe',
    'doc.canvas': 'Strona A4 — przeciągnij, zmień rozmiar; strzałki: 1 mm, Shift: 10 mm',
    'doc.unknown': 'Nieznane pola',
    'doc.resize': 'Zmień rozmiar',
    'doc.confirmDelete': 'Usunąć ten szablon?',
    'doc.discard': 'Odrzucić niezapisane zmiany?',
    'doc.malformed': 'Nieprawidłowa składnia pola {{nazwa}}.',
    'doc.blockCustomer': 'Dane klienta',
    'doc.blockItems': 'Tabela produktów',
    'doc.blockLogo': 'Logo',
    'doc.addBlock': 'Dodaj blok',
    'doc.align': 'Wyrównanie',
    'doc.alignLeft': 'Do lewej',
    'doc.alignCenter': 'Do środka',
    'doc.alignRight': 'Do prawej',
    'doc.size': 'Rozmiar',
    'doc.showPrices': 'Pokaż ceny',
    'doc.insertField': 'Wstaw pole',
    'doc.textLimit': 'Blok tekstu może mieć maksymalnie 4000 znaków.',
    'doc.moveUp': 'W górę',
    'doc.moveDown': 'W dół',
    'doc.removeBlock': 'Usuń blok',
    'doc.logoNone': 'Brak logo',
    'doc.logoChosen': 'Logo wybrane',
    'doc.preview': 'Podgląd',
    'doc.previewOrder': 'Zamówienie do podglądu',
    'doc.statusDirty': 'Niezapisane zmiany',
    'doc.statusSaving': 'Zapisywanie…',
    'doc.statusSaved': 'Zapisano',
    'doc.statusError': 'Błąd: {detail}',
    'doc.empty': 'Szablon jest pusty — dodaj przynajmniej jeden blok z treścią.',
    'doc.previewNoOrders': 'Brak zamówień do podglądu. Dodaj zamówienia do pakowania, aby wyświetlić podgląd.',
    'doc.logoSvg': 'Format SVG nie jest obsługiwany. Użyj pliku PNG lub JPEG.',
    'doc.logoFormat': 'Nieobsługiwany format obrazu. Użyj pliku PNG lub JPEG.',
    'doc.logoTooLarge': 'Logo jest za duże (maks. 2 MB).',
    'doc.logoTotalTooLarge': 'Łączny rozmiar logotypów w szablonie jest za duży (maks. 2 MB).',
    'settings.shippingIntro': 'Dane nadawcy, odbiorcy i punktu odbioru pobieramy automatycznie z Allegro. Adres nadawcy ustaw w książce adresowej Wysyłam z Allegro.',
    'settings.defaultPackageHtml': '<strong>Domyślna paczka</strong> — wartości startowe w widoku pakowania.',
    'sh.length': 'Długość (cm)',
    'sh.width': 'Szerokość (cm)',
    'sh.height': 'Wysokość (cm)',
    'sh.weight': 'Waga (kg)',
    'sh.pageSize': 'Rozmiar etykiety',
    'sh.pdfNote': 'Etykiety są generowane w formacie PDF do wydruku w przeglądarce.',
    'settings.archiveCount': {
      one: '{n} zarchiwizowane zamówienie.',
      few: '{n} zarchiwizowane zamówienia.',
      many: '{n} zarchiwizowanych zamówień.',
    },
    'settings.archiveEmpty': 'Archiwum jest puste.',
    'settings.archiveNoDate': 'brak daty',

    'day.confirm': 'Zakończyć dzień i zarchiwizować wszystkie zamówienia z Gotowe?',
    'day.noneReady': 'Brak zamówień w Gotowe.',
    'day.missingLabels': {
      one: '{n} zamówienie nie ma utworzonej etykiety. Czy na pewno chcesz zakończyć dzień?',
      few: '{n} zamówienia nie mają utworzonej etykiety. Czy na pewno chcesz zakończyć dzień?',
      many: '{n} zamówień nie ma utworzonej etykiety. Czy na pewno chcesz zakończyć dzień?',
    },
    'err.endDay': 'Nie udało się zakończyć dnia',
    'err.sync': 'Synchronizacja nie powiodła się',

    'setup.title': 'Połącz swoje Allegro',
    'setup.intro': 'Skonfiguruj dostęp do Allegro, aby pobierać zamówienia i przygotowywać przesyłki.',
    'setup.checking': 'Sprawdzanie konfiguracji…',
    'setup.createAppHtml': 'Utwórz aplikację w <a href="https://developer.allegro.pl/" target="_blank" rel="noopener noreferrer">panelu deweloperskim Allegro</a> i skopiuj jej dane poniżej.',
    'setup.redirectLabel': 'Adres przekierowania aplikacji Allegro:',
    'setup.envSandbox': 'Środowisko: Allegro Sandbox. Użyj danych aplikacji testowej.',
    'setup.envProduction': 'Środowisko: Allegro. Użyj danych aplikacji produkcyjnej.',
    'setup.saveNote': 'Dane zostaną zapisane na serwerze. Client Secret nie będzie wyświetlany ponownie.',
    'setup.submit': 'Zapisz i kontynuuj',
    'setup.savedTitle': 'Dane Allegro zapisane',
    'setup.saveTokenNote': 'Zachowaj poniższy token dostępu w bezpiecznym miejscu. Weles poprosi o niego przy kolejnym otwarciu aplikacji.',
    'setup.accessTokenLabel': 'Token dostępu Weles',
    'setup.copyToken': 'Kopiuj token',
    'setup.continue': 'Przejdź do aplikacji',
    'setup.retry': 'Sprawdź ponownie',
    'setup.saving': 'Zapisywanie…',
    'setup.savedMsg': 'Dane Allegro zapisane. Zachowaj token dostępu przed przejściem do aplikacji.',
    'setup.saveFailed': 'Nie udało się zapisać konfiguracji.',
    'setup.statusFailed': 'Nie udało się sprawdzić konfiguracji.',
    'setup.tokenCopied': 'Token skopiowany. Zachowaj go w bezpiecznym miejscu.',
    'setup.tokenCopyManual': 'Skopiuj zaznaczony token i zachowaj go w bezpiecznym miejscu.',
  },

  en: {
    'nav.queues': 'Queues',
    'nav.pending': 'Pending',
    'nav.picking': 'Picking',
    'nav.packing': 'Packing',
    'nav.done': 'Done',
    'nav.sync': 'Fetch orders',
    'nav.authorizeAllegro': 'Connect Allegro',
    'nav.reconnectAllegro': 'Reconnect Allegro',
    'nav.endDay': 'End day',
    'nav.settings': 'Settings',
    'nav.language': 'Language',

    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.delete': 'Delete',
    'common.revertTitle': 'Return to pending',
    'common.copyId': 'Copy ID',
    'common.errorPrefix': 'Error',
    'common.requestFailed': 'The request could not be completed. Please try again.',
    'allegro.not_authorized': 'Reconnect Allegro to continue.',
    'common.allegro_unreachable': 'Allegro cannot be reached. Please try again later.',
    'allegro.request_failed': 'The Allegro request failed. Please try again.',

    'unit.order': { one: 'order', other: 'orders' },
    'unit.product': { one: 'product', other: 'products' },
    'unit.transaction': { one: 'transaction', other: 'transactions' },

    'category.locker': 'InPost parcel locker',
    'category.other': 'Other',

    'banner.problem': 'There is a problem with the application state.',
    'banner.quarantined': {
      one: '{n} record was skipped — it failed validation.',
      other: '{n} records were skipped — they failed validation.',
    },

    'token.prompt': 'Enter the PACKING_ACCESS_TOKEN from the .env file:',
    'token.required': 'An access token is required.',

    'print.popupBlocked': 'The browser is blocking the print window. Allow pop-ups and try again.',

    'pending.title': 'Pending orders',
    'pending.createList': 'Create picking list',
    'pending.selectHint': 'Select products',
    'pending.emptyLead': 'No pending orders. Click "Fetch orders"',
    'pending.emptyOr': 'or',
    'pending.seedSample': 'Load sample orders',
    'pending.transactionCount': { one: '{n} transaction', other: '{n} transactions' },
    'err.createList': 'Could not create the list',
    'err.seedSample': 'Could not load sample orders',

    'picking.title': 'Picking',
    'picking.empty': 'No active picking lists.',
    'picking.orderCount': { one: '{n} order', other: '{n} orders' },
    'picking.rename': 'Rename',
    'picking.print': 'Print list',
    'picking.start': 'Pack →',
    'picking.printTitle': 'List: {name}',
    'picking.printProduct': 'Product',
    'picking.printQty': 'Quantity',
    'err.rename': 'Could not rename the list',
    'err.revertList': 'Could not revert the list',
    'err.startPacking': 'Could not move to packing',

    'packing.title': 'Packing',
    'packing.empty': 'No orders to pack. Move a picking list to packing.',
    'packing.prev': 'Previous',
    'packing.next': 'Next',
    'packing.trackingLabel': 'Tracking number:',
    'packing.lockerLegend': 'InPost parcel locker — parcel size',
    'packing.sizeA': 'Small (8×38×64 cm)',
    'packing.sizeB': 'Medium (19×38×64 cm)',
    'packing.sizeC': 'Large (41×38×64 cm)',
    'packing.dims': 'Dimensions (cm)',
    'packing.weight': 'Weight (kg)',
    'packing.selectSizeNote': 'Choose a parcel size (A, B or C) to create an InPost parcel locker label.',
    'packing.savingSize': 'Saving parcel size…',
    'packing.saveError': 'Could not save the parcel size: {detail}',
    'packing.labelLocker': 'Parcel locker label',
    'packing.labelCourier': 'Courier label',
    'packing.invoice': 'Document',
    'packing.customDoc': 'Custom document',
    'packing.done': 'DONE',
    'packing.generatingLabel': 'Generating label…',
    'packing.doneConfirm': 'The label has not been printed — mark the order as done anyway?',
    'err.revertOrder': 'Could not revert the order',
    'err.copyId': 'Could not copy the ID',
    'err.label': 'Could not download the label',
    'err.document': 'Could not generate the document',
    'err.done': 'Could not mark the order as done',

    'done.title': 'Done ({n})',
    'done.empty': 'No completed orders.',
    'done.labelCreated': 'Label created',
    'done.labelMissing': '— no label —',
    'done.undo': 'Undo',

    'settings.title': 'Settings',
    'settings.documentEditor': 'A4 document editor',
    'settings.documentEditorDesc': 'Design a PDF document, insert placeholders and import or export JSON templates.',
    'settings.openDocumentEditor': 'Go to document editor',
    'doc.blockPanel': 'Blocks and placeholders',
    'settings.tabDocuments': 'Documents',
    'settings.tabShipping': 'Shipping',
    'settings.tabArchive': 'Archive',
    'settings.docsIntro': 'Select the fields to show on the printout.',
    'inv.buyerName': 'Buyer name',
    'inv.buyerAddress': 'Buyer address',
    'inv.items': 'Product list',
    'inv.price': 'Unit price',
    'inv.courier': 'Courier',
    'inv.pickupPoint': 'Pickup point (parcel locker)',
    'inv.allegroId': 'Allegro order number',
    'inv.freeTextLabel': 'Custom text (max 160 characters)',
    'inv.freeTextPlaceholder': 'e.g. Thank you for your purchase!',
    'settings.customDocDesc': 'Custom PDF document — printed with the "Custom document" button while packing.',
    'settings.docUploaded': 'Document uploaded',
    'settings.docNone': 'No document',
    'settings.docReplace': 'Replace file',
    'settings.docChoose': 'Choose a PDF file',
    'settings.docUploadedOk': 'Uploaded successfully',
    'settings.saved': 'Saved',
    'settings.error': 'Error',
    'err.docDelete': 'Could not delete the document',

    'doc.source': 'Document source',
    'doc.sourceUpload': 'Uploaded PDF',
    'doc.sourceTemplate': 'Designed template',
    'doc.templateName': 'Template name',
    'doc.blockHeading': 'Heading',
    'doc.blockType': 'Block type',
    'doc.blockText': 'Text',
    'doc.blockPlaceholder': 'Placeholder',
    'doc.blockLine': 'Line',
    'doc.bold': 'Bold',
    'doc.templates': 'Templates',
    'doc.duplicate': 'Duplicate',
    'doc.export': 'Export current',
    'doc.exportAll': 'Export all',
    'doc.import': 'Import JSON',
    'doc.importConflict': 'Import template conflicts',
    'doc.importRename': 'Rename on conflict',
    'doc.importOverwrite': 'Overwrite on conflict',
    'doc.importInvalid': 'Invalid JSON file.',
    'doc.imported': 'Templates imported: {count}',
    'doc.deleteTemplate': 'Delete template',
    'doc.sample': 'Sample data',
    'doc.canvas': 'A4 page — drag, resize; arrows: 1 mm, Shift: 10 mm',
    'doc.unknown': 'Unknown placeholders',
    'doc.resize': 'Resize',
    'doc.confirmDelete': 'Delete this template?',
    'doc.discard': 'Discard unsaved changes?',
    'doc.malformed': 'Invalid placeholder syntax; use {{name}}.',
    'doc.blockCustomer': 'Customer details',
    'doc.blockItems': 'Product table',
    'doc.blockLogo': 'Logo',
    'doc.addBlock': 'Add block',
    'doc.align': 'Alignment',
    'doc.alignLeft': 'Left',
    'doc.alignCenter': 'Center',
    'doc.alignRight': 'Right',
    'doc.size': 'Size',
    'doc.showPrices': 'Show prices',
    'doc.insertField': 'Insert field',
    'doc.textLimit': 'A text block can contain at most 4000 characters.',
    'doc.moveUp': 'Move up',
    'doc.moveDown': 'Move down',
    'doc.removeBlock': 'Remove block',
    'doc.logoNone': 'No logo',
    'doc.logoChosen': 'Logo selected',
    'doc.preview': 'Preview',
    'doc.previewOrder': 'Preview order',
    'doc.statusDirty': 'Unsaved changes',
    'doc.statusSaving': 'Saving…',
    'doc.statusSaved': 'Saved',
    'doc.statusError': 'Error: {detail}',
    'doc.empty': 'The template is empty — add at least one block with content.',
    'doc.previewNoOrders': 'No orders to preview. Add orders to packing to see a preview.',
    'doc.logoSvg': 'SVG is not supported. Use a PNG or JPEG file.',
    'doc.logoFormat': 'Unsupported image format. Use a PNG or JPEG file.',
    'doc.logoTooLarge': 'The logo is too large (max 2 MB).',
    'doc.logoTotalTooLarge': 'The combined logo size in the template is too large (max 2 MB).',
    'settings.shippingIntro': 'Sender, recipient and pickup point details are read automatically from Allegro. Set the sender address in the "Wysyłam z Allegro" address book.',
    'settings.defaultPackageHtml': '<strong>Default parcel</strong> — starting values in the packing view.',
    'sh.length': 'Length (cm)',
    'sh.width': 'Width (cm)',
    'sh.height': 'Height (cm)',
    'sh.weight': 'Weight (kg)',
    'sh.pageSize': 'Label size',
    'sh.pdfNote': 'Labels are generated as PDF files for printing in the browser.',
    'settings.archiveCount': {
      one: '{n} archived order.',
      other: '{n} archived orders.',
    },
    'settings.archiveEmpty': 'The archive is empty.',
    'settings.archiveNoDate': 'no date',

    'day.confirm': 'End the day and archive every Done order?',
    'day.noneReady': 'There are no Done orders.',
    'day.missingLabels': {
      one: '{n} order has no label yet. End the day anyway?',
      other: '{n} orders have no label yet. End the day anyway?',
    },
    'err.endDay': 'Could not end the day',
    'err.sync': 'Synchronization failed',

    'setup.title': 'Connect your Allegro',
    'setup.intro': 'Configure access to Allegro to fetch orders and prepare shipments.',
    'setup.checking': 'Checking configuration…',
    'setup.createAppHtml': 'Create an application in the <a href="https://developer.allegro.pl/" target="_blank" rel="noopener noreferrer">Allegro developer panel</a> and copy its details below.',
    'setup.redirectLabel': 'Allegro application redirect URI:',
    'setup.envSandbox': 'Environment: Allegro Sandbox. Use the test application credentials.',
    'setup.envProduction': 'Environment: Allegro. Use the production application credentials.',
    'setup.saveNote': 'The details are saved on the server. The Client Secret will not be shown again.',
    'setup.submit': 'Save and continue',
    'setup.savedTitle': 'Allegro details saved',
    'setup.saveTokenNote': 'Keep the access token below in a safe place. Weles will ask for it the next time you open the application.',
    'setup.accessTokenLabel': 'Weles access token',
    'setup.copyToken': 'Copy token',
    'setup.continue': 'Go to the application',
    'setup.retry': 'Check again',
    'setup.saving': 'Saving…',
    'setup.savedMsg': 'Allegro details saved. Keep the access token before continuing to the application.',
    'setup.saveFailed': 'Could not save the configuration.',
    'setup.statusFailed': 'Could not check the configuration.',
    'setup.tokenCopied': 'Token copied. Keep it in a safe place.',
    'setup.tokenCopyManual': 'Copy the selected token and keep it in a safe place.',
  },
};

let currentLanguage = DEFAULT_LANGUAGE;

// Text that depends on live state (counts, in-flight operations) rather than a
// single catalog key. Registering a render function here lets a language switch
// rewrite the node in place without re-rendering the view.
const dynamicText = new Map();

function normalizeLanguage(value) {
  if (!value) return null;
  const base = String(value).trim().toLowerCase().split(/[-_]/)[0];
  return SUPPORTED_LANGUAGES.indexOf(base) >= 0 ? base : null;
}

function readStoredLanguage() {
  try {
    if (typeof localStorage === 'undefined' || !localStorage) return null;
    return normalizeLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY));
  } catch {
    return null;
  }
}

function persistLanguage(lang) {
  try {
    if (typeof localStorage === 'undefined' || !localStorage) return;
    localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
  } catch {
    // Storage may be blocked (private mode, disabled cookies). The choice still
    // applies for this session; it is simply not remembered.
  }
}

function languageLocale(lang) {
  return LOCALES[lang || currentLanguage] || LOCALES[DEFAULT_LANGUAGE];
}

function pluralCategory(lang, count) {
  const n = Number(count);
  if (!Number.isFinite(n)) return 'other';
  try {
    if (typeof Intl !== 'undefined' && Intl.PluralRules) return new Intl.PluralRules(lang).select(n);
  } catch {
    // Fall through to a minimal English-style rule.
  }
  return n === 1 ? 'one' : 'other';
}

function interpolate(template, vars) {
  return String(template).replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match);
}

function t(key, vars = {}, count) {
  const table = MESSAGES[currentLanguage] || MESSAGES[DEFAULT_LANGUAGE];
  let entry = table[key];
  if (entry === undefined) entry = MESSAGES[DEFAULT_LANGUAGE][key];
  if (entry === undefined) return key;
  const values = vars || {};
  if (entry !== null && typeof entry === 'object') {
    const n = count === undefined ? values.n : count;
    const category = pluralCategory(currentLanguage, n === undefined ? 0 : n);
    entry = entry[category] !== undefined ? entry[category]
      : entry.other !== undefined ? entry.other
        : entry.many !== undefined ? entry.many
          : entry.one !== undefined ? entry.one
            : Object.values(entry)[0];
  }
  return interpolate(entry, values);
}

// App-owned delivery categories are localized; carrier names coming from
// Allegro pass through unchanged.
function categoryLabel(category) {
  if (category === 'Paczkomat InPost') return t('category.locker');
  if (category === 'Inny') return t('category.other');
  return category;
}

function formatDateTime(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(languageLocale());
}

function formatNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toLocaleString(languageLocale());
}

function getLanguage() {
  return currentLanguage;
}

function translationVars(node) {
  const raw = node.getAttribute('data-i18n-vars');
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function translationCount(node) {
  const raw = node.getAttribute('data-i18n-count');
  if (raw === null || raw === undefined) return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

function applyTextNode(node) {
  const key = node.getAttribute('data-i18n');
  if (!key) return;
  node.textContent = t(key, translationVars(node), translationCount(node));
}

// Render helper for nodes whose key/vars are only known at runtime. It writes
// the attributes so a later language switch can recompute the same text.
function setText(node, key, vars, count) {
  if (!node) return;
  node.setAttribute('data-i18n', key);
  if (vars && Object.keys(vars).length) node.setAttribute('data-i18n-vars', JSON.stringify(vars));
  else node.removeAttribute('data-i18n-vars');
  if (count === undefined || count === null) node.removeAttribute('data-i18n-count');
  else node.setAttribute('data-i18n-count', String(count));
  node.textContent = t(key, vars || {}, count === undefined ? undefined : count);
}

function bindDynamicText(node, render) {
  if (!node) return;
  node.textContent = render();
  dynamicText.set(node, render);
}

// Like dynamicText, but for text outside the re-rendered content: the state
// banner, the setup status line and form notes. renderQueue() clears dynamicText
// on every view rebuild, so chrome that outlives a render keeps its render
// function here instead. A render function tracks the selected language; raw
// text (an upstream error) is deliberately never bound so it cannot be
// machine-translated.
const staticText = new Map();

function bindStaticText(node, render) {
  if (!node) return;
  node.textContent = render();
  staticText.set(node, render);
}

function clearStaticText(node) {
  if (node) staticText.delete(node);
}

// Status line under a form: a render function keeps catalog text in sync with
// the language, a raw string is shown verbatim. kind selects the status dot
// color (ok = success, error = danger); the text itself carries no symbols.
function showNote(node, content, kind = 'ok') {
  if (!node) return;
  if (typeof content === 'function') bindStaticText(node, content);
  else { clearStaticText(node); node.textContent = content; }
  node.classList.toggle('note-error', kind === 'error');
  node.classList.remove('hidden');
}

function syncLanguageControls(root) {
  const scope = root || (typeof document !== 'undefined' ? document : null);
  if (!scope || !scope.querySelectorAll) return;
  scope.querySelectorAll('[data-lang-select]').forEach(select => { select.value = currentLanguage; });
}

function applyDocumentLanguage() {
  if (typeof document !== 'undefined' && document && document.documentElement) {
    document.documentElement.lang = currentLanguage;
  }
}

// Rewrite already-rendered nodes in place. Nothing is re-fetched or rebuilt, so
// selections, unsaved form values, the packing carousel and in-flight
// operations all survive a language switch.
function applyLanguage(root) {
  const scope = root || (typeof document !== 'undefined' ? document : null);
  if (scope && scope.querySelectorAll) {
    scope.querySelectorAll('[data-i18n]').forEach(applyTextNode);
    scope.querySelectorAll('[data-i18n-html]').forEach(node => {
      node.innerHTML = t(node.getAttribute('data-i18n-html'));
    });
    scope.querySelectorAll('[data-i18n-title]').forEach(node => {
      node.title = t(node.getAttribute('data-i18n-title'));
    });
    scope.querySelectorAll('[data-i18n-placeholder]').forEach(node => {
      node.placeholder = t(node.getAttribute('data-i18n-placeholder'));
    });
    scope.querySelectorAll('[data-i18n-aria]').forEach(node => {
      node.setAttribute('aria-label', t(node.getAttribute('data-i18n-aria')));
    });
    syncLanguageControls(scope);
  }
  dynamicText.forEach((render, node) => { node.textContent = render(); });
  staticText.forEach((render, node) => {
    // Drop bindings for nodes a re-render replaced; writing to a detached node
    // would also leak the old element.
    if (node.isConnected === false) { staticText.delete(node); return; }
    node.textContent = render();
  });
}

function setLanguage(lang, options = {}) {
  const normalized = normalizeLanguage(lang);
  if (!normalized) return false;
  currentLanguage = normalized;
  persistLanguage(normalized);
  applyDocumentLanguage();
  applyLanguage(options.root);
  return true;
}

// Remembered preference from a previous visit, otherwise Polish — deliberately
// not derived from navigator.language.
currentLanguage = readStoredLanguage() || DEFAULT_LANGUAGE;

async function promptForAccessToken() {
  if (accessToken) return accessToken;
  if (!accessTokenPrompt) {
    accessTokenPrompt = Promise.resolve().then(() => {
      const entered = window.prompt(t('token.prompt'));
      if (!entered || !entered.trim()) throw new Error(t('token.required'));
      setAccessToken(entered.trim());
      return accessToken;
    }).finally(() => { accessTokenPrompt = null; });
  }
  return accessTokenPrompt;
}

async function apiFetch(path, options = {}) {
  const send = token => {
    const headers = new Headers(options.headers || {});
    // Every application request (JSON, PDF, setup, OAuth initiation) tells the
    // backend which language to answer in.
    headers.set('Accept-Language', currentLanguage);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return fetch(`${API}${path}`, { ...options, headers }).catch(() => {
      throw new Error(t('common.requestFailed'));
    });
  };

  const sentToken = accessToken;
  let res = await send(sentToken);
  if (res.status === 401 && accessToken === sentToken) clearAccessToken();
  if (res.status !== 401 || res.headers.get('X-Packing-Auth-Required') !== '1') return res;

  const token = await promptForAccessToken();
  res = await send(token);
  if (res.status === 401 && accessToken === token) clearAccessToken();
  return res;
}

// Uniform monochrome outline icons (inline SVG, stroke currentColor). UI chrome
// never uses emoji glyphs.
const ICONS = {
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
  chevronLeft: '<polyline points="15 18 9 12 15 6"/>',
  chevronRight: '<polyline points="9 18 15 12 9 6"/>',
  print: '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  pencil: '<path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
  revert: '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
};

function icon(name, extraClass = '') {
  const cls = extraClass ? `icon ${extraClass}` : 'icon';
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
}

// Escape every value that came from the API (Allegro data and settings) before it
// reaches innerHTML. Allegro product names and buyer fields are untrusted input.
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// Known app-owned codes follow the selected language. Older plain-text errors
// remain supported; malformed bodies never turn into JSON or HTTP status text.
function apiErrorMessage(payload) {
  const detail = payload && (payload.detail ?? payload.message);
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    if (['allegro.not_authorized', 'common.allegro_unreachable', 'allegro.request_failed'].includes(detail.code)) {
      return t(detail.code);
    }
    return typeof detail.message === 'string' && detail.message.trim()
      ? detail.message : t('common.requestFailed');
  }
  return typeof detail === 'string' && detail.trim() ? detail : t('common.requestFailed');
}

async function responseError(res) {
  let payload = null;
  try { payload = await res.json(); } catch { /* HTML, empty or malformed response */ }
  return new Error(apiErrorMessage(payload));
}

let toastTimer = null;
function showToast(message, kind = 'info') {
  const info = document.getElementById('toast-info');
  const error = document.getElementById('toast-error');
  if (!info || !error) return;
  clearTimeout(toastTimer);
  [info, error].forEach(node => {
    clearStaticText(node);
    node.textContent = '';
  });
  const node = kind === 'error' ? error : info;
  bindStaticText(node, typeof message === 'function' ? message : () => String(message));
  toastTimer = setTimeout(() => {
    clearStaticText(node);
    node.textContent = '';
    toastTimer = null;
  }, kind === 'error' ? 8000 : 5000);
}

// All API calls go through here: a failed request raises instead of silently
// re-rendering the same stale queue.
async function api(path, options = {}) {
  const res = await apiFetch(path, options);
  const type = res.headers.get('content-type') || '';
  let payload = null;
  if (type.includes('application/json')) {
    try { payload = await res.json(); } catch { payload = null; }
  }
  if (!res.ok) {
    throw new Error(apiErrorMessage(payload));
  }
  return payload;
}

function reportError(prefix, err) {
  showToast(`${prefix}\n${err && typeof err.message === 'string' ? err.message : t('common.requestFailed')}`, 'error');
}

// PDFs are fetched first so a failure (401/502/404) shows up as a message instead of
// a browser tab full of JSON. `options` lets callers POST a draft (document preview)
// through the same popup-timing and error handling. beforeFetch can create a
// label after reserving the popup, before downloading its PDF.
async function openPdf(path, options = {}, beforeFetch = null) {
  // Reserve the tab during the click; browsers block popups after a slow API call.
  const printTab = window.open('about:blank', '_blank');
  if (!printTab) throw new Error(t('print.popupBlocked'));
  printTab.opener = null;
  try {
    if (beforeFetch) await beforeFetch();
    const res = await apiFetch(path, options);
    if (!res.ok) {
      throw await responseError(res);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    printTab.location.replace(url);
  } catch (err) {
    printTab.close();
    throw err;
  }
}

let state = {
  orders: [],         // all orders from backend
  pickingLists: [],   // all picking lists
  currentQueue: 'pending',
  currentCourier: null, // courier filter for pending view
  selectedOrderIds: new Set(),  // for pending → picking list creation
  packingQueue: [],      // orders currently in packing carousel
  packingIndex: 0,       // which card is shown
  packingDirection: null, // 'next' | 'prev' | null
  settingsTab: 'documents',
  customDocAvailable: false,
  shipmentSettings: null, // sender + package defaults for the packing view
  parcelSizeSaves: new Map(),
  parcelSizeErrors: new Map(),
  dryRun: false,        // PACKING_SHIPMENT_DRY_RUN — enables test-only actions
  authorized: false,    // Allegro session state, shown on the auth button
};

// ---- Fetch ----

function renderStateBanner(status) {
  const el = document.getElementById('state-banner');
  if (!el) return;
  let render = null;
  if (status && status.ok === false) {
    // The backend sends an app-owned, already-worded message. Keep it as
    // diagnostic detail beside a generic prefix that follows the language,
    // rather than guessing a translation for arbitrary text.
    const detail = status.message ? String(status.message) : '';
    render = () => t('banner.problem') + (detail ? ' ' + detail : '');
  } else if (status && status.quarantined) {
    const n = status.quarantined;
    render = () => t('banner.quarantined', { n });
  }
  if (!render) {
    clearStaticText(el);
    el.classList.add('hidden');
    el.textContent = '';
    return;
  }
  el.classList.remove('hidden');
  bindStaticText(el, render);
}

async function fetchAll() {
  try {
    const [orders, lists, settings, status] = await Promise.all([
      api('/orders/'),
      api('/picking-lists'),
      api('/print/shipment-settings'),
      api('/orders/status'),
    ]);
    state.orders = orders;
    state.pickingLists = lists;
    state.shipmentSettings = settings;
    state.dryRun = Boolean(status && status.dry_run);
    renderStateBanner(status);
  } catch (err) {
    renderStateBanner({ ok: false, message: err.message });
    return;
  }
  updateBadges();
  renderQueue(state.currentQueue);
}


function deliveryCategory(order) {
  return order.delivery_type === 'inpost_locker' ? 'Paczkomat InPost' : (order.courier || 'Inny');
}

// ---- Badges ----

function updateBadges() {
  const counts = { pending: 0, picking: 0, packing: 0, done: 0 };
  state.orders.forEach(o => counts[o.status]++);
  Object.entries(counts).forEach(([k, v]) => {
    document.getElementById(`count-${k}`).textContent = formatNumber(v);
  });

  // Inject courier sub-items under Oczekujące
  const pendingOrders = state.orders.filter(o => o.status === 'pending');
  const courierCounts = {};
  pendingOrders.forEach(o => {
    const c = deliveryCategory(o);
    courierCounts[c] = (courierCounts[c] || 0) + 1;
  });

  const existing = document.getElementById('courier-subnav');
  if (existing) existing.remove();

  const couriers = Object.keys(courierCounts);
  if (couriers.length <= 1 && !courierCounts['Paczkomat InPost']) return;

  const ul = document.createElement('ul');
  ul.id = 'courier-subnav';
  couriers.forEach(courier => {
    const li = document.createElement('li');
    li.className = 'courier-nav-item' + (state.currentCourier === courier ? ' active' : '');
    // The translation key goes on the inner label, never on the li: translating
    // the li would assign textContent and drop the badge child.
    const label = document.createElement('span');
    label.className = 'courier-nav-label';
    const key = courier === 'Paczkomat InPost' ? 'category.locker'
      : courier === 'Inny' ? 'category.other' : null;
    if (key) setText(label, key);
    else label.textContent = courier;
    const badge = document.createElement('span');
    badge.className = 'badge badge-dim';
    badge.textContent = courierCounts[courier];
    li.appendChild(label);
    li.appendChild(badge);
    li.addEventListener('click', (e) => {
      e.stopPropagation();
      state.currentCourier = state.currentCourier === courier ? null : courier;
      updateBadges();
      renderQueue('pending');
    });
    ul.appendChild(li);
  });

  const pendingItem = document.querySelector('[data-queue="pending"]');
  pendingItem.after(ul);
}

// ---- Routing ----

function renderQueue(queue) {
  state.currentQueue = queue;
  if (queue !== 'pending') state.currentCourier = null;
  dynamicText.clear();
  document.querySelectorAll('.queue-item').forEach(el => {
    el.classList.toggle('active', el.dataset.queue === queue);
  });
  const btnSettings = document.getElementById('btn-settings');
  if (btnSettings) btnSettings.classList.toggle('active', queue === 'settings');
  const content = document.getElementById('content');

  if (queue === 'pending') renderPending(content);
  else if (queue === 'picking') renderPicking(content);
  else if (queue === 'packing') renderPacking(content);
  else if (queue === 'done') renderDone(content);
  else if (queue === 'settings') renderSettings(content);
}

// ---- Pending view ----

function selectedCountText(products, orders) {
  if (!products) return t('pending.selectHint');
  return `${products} ${t('unit.product', {}, products)} — ${orders} ${t('unit.order', {}, orders)}`;
}

function renderPending(el) {
  const orders = state.orders.filter(o =>
    o.status === 'pending' &&
    (!state.currentCourier || (deliveryCategory(o)) === state.currentCourier)
  );
  state.selectedOrderIds.clear();

  el.innerHTML = `
    <h2 data-i18n="pending.title">${t('pending.title')}</h2>
    <div id="pending-toolbar">
      <button class="btn btn-primary" id="btn-create-pl" disabled data-i18n="pending.createList">
        ${t('pending.createList')}
      </button>
      <span id="selected-count" class="count-hint">${t('pending.selectHint')}</span>
    </div>
    <div class="order-list" id="order-list"></div>
  `;

  const list = el.querySelector('#order-list');
  const countEl = el.querySelector('#selected-count');

  if (!orders.length) {
    // Seeding sample orders is a dry-run affordance. On a real instance the
    // backend rejects it, so the button must not be offered at all.
    const seedAction = state.dryRun
      ? ` ${t('pending.emptyOr')} <button class="btn btn-secondary btn-inline" id="btn-seed-sample" data-i18n="pending.seedSample">${t('pending.seedSample')}</button>`
      : '';
    list.innerHTML = `<p class="empty"><span data-i18n="pending.emptyLead">${t('pending.emptyLead')}</span>${seedAction}.</p>`;
    const seedBtn = list.querySelector('#btn-seed-sample');
    if (seedBtn) {
      seedBtn.addEventListener('click', async () => {
        seedBtn.disabled = true;
        try {
          await api('/orders/seed-mock', { method: 'POST' });
          await fetchAll();
          renderQueue('pending');
        } catch (err) {
          reportError(t('err.seedSample'), err);
        }
      });
    }
    return;
  }

  // Group orders by courier
  const byCourier = {};
  orders.forEach(order => {
    const courier = deliveryCategory(order);
    if (!byCourier[courier]) byCourier[courier] = [];
    byCourier[courier].push(order);
  });

  // Track which products are selected (globally across couriers)
  const selectedProducts = new Set();
  const productMap = {};

  Object.entries(byCourier).forEach(([courier, courierOrders]) => {
    // Section header — only show when viewing all couriers
    if (!state.currentCourier) {
      const header = document.createElement('div');
      header.className = 'courier-header';
      header.textContent = categoryLabel(courier);
      if (courier === 'Paczkomat InPost') header.setAttribute('data-i18n', 'category.locker');
      else if (courier === 'Inny') header.setAttribute('data-i18n', 'category.other');
      list.appendChild(header);
    }

    // Aggregate by product name within this courier
    const courierProductMap = {};
    courierOrders.forEach(order => {
      order.items.forEach(item => {
        if (!courierProductMap[item.name]) courierProductMap[item.name] = { qty: 0, orderIds: new Set() };
        courierProductMap[item.name].qty += item.quantity;
        courierProductMap[item.name].orderIds.add(order.id);
        // Keep products from different delivery categories separate.
        const key = JSON.stringify([courier, item.name]);
        if (!productMap[key]) productMap[key] = { qty: 0, orderIds: new Set() };
        productMap[key].qty += item.quantity;
        productMap[key].orderIds.add(order.id);
      });
    });

    Object.entries(courierProductMap).forEach(([name, data]) => {
      const productKey = JSON.stringify([courier, name]);
      const txCount = data.orderIds.size;
      const card = document.createElement('div');
      card.className = 'order-card';
      card.innerHTML = `
        <input type="checkbox" />
        <div class="order-info">
          <div class="buyer">${data.qty}x ${esc(name)}</div>
          <div class="address" style="margin-top:4px"><span data-i18n="pending.transactionCount" data-i18n-count="${txCount}" data-i18n-vars='{"n":${txCount}}'>${t('pending.transactionCount', { n: txCount }, txCount)}</span></div>
        </div>
      `;
      const cb = card.querySelector('input');
      cb.addEventListener('change', () => {
        if (cb.checked) {
          selectedProducts.add(productKey);
          card.classList.add('selected');
        } else {
          selectedProducts.delete(productKey);
          card.classList.remove('selected');
        }

        state.selectedOrderIds.clear();
        selectedProducts.forEach(pName => {
          productMap[pName].orderIds.forEach(id => state.selectedOrderIds.add(id));
        });

        const n = selectedProducts.size;
        document.getElementById('btn-create-pl').disabled = n === 0;
        countEl.textContent = selectedCountText(n, state.selectedOrderIds.size);
      });
      list.appendChild(card);
    });
  });

  bindDynamicText(countEl, () => selectedCountText(selectedProducts.size, state.selectedOrderIds.size));

  el.querySelector('#btn-create-pl').addEventListener('click', async () => {
    if (!state.selectedOrderIds.size) return;
    try {
      await api('/picking-lists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: '', order_ids: [...state.selectedOrderIds] }),
      });
    } catch (err) {
      reportError(t('err.createList'), err);
      return;
    }
    await fetchAll();
    renderQueue('picking');
  });
}

// ---- Picking view ----

function renderPicking(el) {
  el.innerHTML = `<h2 data-i18n="picking.title">${t('picking.title')}</h2><div class="order-list" id="pl-list"></div>`;
  const list = el.querySelector('#pl-list');

  if (!state.pickingLists.length) {
    list.innerHTML = `<p class="empty" data-i18n="picking.empty">${t('picking.empty')}</p>`;
    return;
  }

  state.pickingLists.forEach(pl => {
    const orderCount = pl.order_ids.length;
    const card = document.createElement('div');
    card.className = 'picking-card';
    card.innerHTML = `
      <div class="pl-info">
        <div class="pl-name-wrap">
          <span class="pl-name" data-id="${pl.id}">${esc(pl.name)}</span>
          <span class="pl-count" data-i18n="picking.orderCount" data-i18n-count="${orderCount}" data-i18n-vars='{"n":${orderCount}}'>${t('picking.orderCount', { n: orderCount }, orderCount)}</span>
        </div>
        <div class="pl-rename hidden" data-id="${pl.id}">
          <input class="pl-rename-input" type="text" value="${esc(pl.name)}" />
          <button class="btn btn-primary btn-rename-confirm" data-id="${pl.id}" data-i18n="common.save">${t('common.save')}</button>
          <button class="btn btn-secondary btn-rename-cancel" data-i18n="common.cancel">${t('common.cancel')}</button>
        </div>
      </div>
      <div class="pl-actions">
        <button class="btn-icon-red btn-revert" data-id="${pl.id}" data-i18n-title="common.revertTitle" data-i18n-aria="common.revertTitle" aria-label="${esc(t('common.revertTitle'))}" title="${esc(t('common.revertTitle'))}">${icon('revert')}</button>
        <button class="btn btn-secondary btn-rename-toggle" data-id="${pl.id}">${icon('pencil')}<span data-i18n="picking.rename">${t('picking.rename')}</span></button>
        <button class="btn btn-secondary btn-print-pl" data-id="${pl.id}">${icon('print')}<span data-i18n="picking.print">${t('picking.print')}</span></button>
        <button class="btn btn-primary btn-start-pack" data-id="${pl.id}" data-i18n="picking.start">${t('picking.start')}</button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll('.btn-revert').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api(`/picking-lists/${btn.dataset.id}/revert`, { method: 'POST' });
      } catch (err) {
        reportError(t('err.revertList'), err);
        return;
      }
      await fetchAll();
      renderQueue('picking');
    });
  });

  list.querySelectorAll('.btn-rename-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.picking-card');
      card.querySelector('.pl-name-wrap').classList.toggle('hidden');
      const renameDiv = card.querySelector('.pl-rename');
      renameDiv.classList.toggle('hidden');
      if (!renameDiv.classList.contains('hidden')) {
        const input = renameDiv.querySelector('.pl-rename-input');
        input.addEventListener('keydown', e => e.stopPropagation());
        input.focus();
        input.select();
      }
    });
  });

  list.querySelectorAll('.btn-rename-cancel').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.picking-card');
      card.querySelector('.pl-name-wrap').classList.remove('hidden');
      card.querySelector('.pl-rename').classList.add('hidden');
    });
  });

  list.querySelectorAll('.btn-rename-confirm').forEach(btn => {
    btn.addEventListener('click', async () => {
      const card = btn.closest('.picking-card');
      const newName = card.querySelector('.pl-rename-input').value.trim();
      if (!newName) return;
      try {
        await api(`/picking-lists/${btn.dataset.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName }),
        });
      } catch (err) {
        reportError(t('err.rename'), err);
        return;
      }
      await fetchAll();
      renderQueue('picking');
    });
  });

  list.querySelectorAll('.btn-start-pack').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api(`/picking-lists/${btn.dataset.id}/start-packing`, { method: 'POST' });
      } catch (err) {
        reportError(t('err.startPacking'), err);
        return;
      }
      await fetchAll();
      renderQueue('packing');
    });
  });

  list.querySelectorAll('.btn-print-pl').forEach(btn => {
    btn.addEventListener('click', () => printPickingList(btn.dataset.id));
  });
}

function printPickingList(plId) {
  const pl = state.pickingLists.find(p => p.id === plId);
  if (!pl) return;

  const orders = state.orders.filter(o => pl.order_ids.includes(o.id));

  // Consolidate items across orders
  const consolidated = {};
  orders.forEach(o => {
    o.items.forEach(item => {
      consolidated[item.name] = (consolidated[item.name] || 0) + item.quantity;
    });
  });

  const rows = Object.entries(consolidated).map(([name, qty]) =>
    `<tr><td>${esc(name)}</td><td>${qty}</td></tr>`
  ).join('');

  const win = window.open('', '_blank');
  win.document.write(`<!DOCTYPE html><html lang="${currentLanguage}"><head><title>${esc(pl.name)}</title>
    <style>body{font-family:Arial;margin:40px}table{width:100%;border-collapse:collapse}
    td,th{border:1px solid #ccc;padding:8px}th{background:#eee}</style></head>
    <body><h2>${esc(t('picking.printTitle', { name: pl.name }))}</h2>
    <table><thead><tr><th>${esc(t('picking.printProduct'))}</th><th>${esc(t('picking.printQty'))}</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <script>window.onload=()=>window.print()<\/script></body></html>`);
  win.document.close();
}

// ---- Packing view ----

function renderPacking(el) {
  state.packingQueue = state.orders.filter(o => o.status === 'packing');
  state.packingIndex = Math.min(state.packingIndex, Math.max(0, state.packingQueue.length - 1));
  renderPackingCard(el);
}

function parcelSizeStatusText(order) {
  const pendingSize = state.parcelSizeSaves.get(order.id);
  if (pendingSize) return t('packing.savingSize');
  const error = state.parcelSizeErrors.get(order.id);
  if (error) return t(error.key, error.vars);
  return '';
}

function labelButtonText(isLocker, printed, busy) {
  if (busy) return t('packing.generatingLabel');
  // A printed state is conveyed by the button's styling (.printed), not text.
  return isLocker ? t('packing.labelLocker') : t('packing.labelCourier');
}

function renderPackingCard(el) {
  const orders = state.packingQueue;

  el.innerHTML = `<h2 data-i18n="packing.title">${t('packing.title')}</h2><div id="packing-view"></div>`;
  const view = el.querySelector('#packing-view');
  dynamicText.clear();

  if (!orders.length) {
    view.innerHTML = `<p class="empty" data-i18n="packing.empty">${t('packing.empty')}</p>`;
    return;
  }

  const idx = state.packingIndex;
  const order = orders[idx];

  const animClass = state.packingDirection === 'next' ? 'animate-next'
                  : state.packingDirection === 'prev' ? 'animate-prev' : '';
  state.packingDirection = null;

  const pkg = (state.shipmentSettings && state.shipmentSettings.package) || {};
  const isLocker = order.delivery_type === 'inpost_locker';
  const pendingSize = state.parcelSizeSaves.get(order.id);
  const selectedSize = pendingSize ? pendingSize.value : order.parcel_size;
  const lockerNeedsSize = isLocker && !order.shipment_id && !selectedSize;

  view.innerHTML = `
    <div class="pack-nav">
      <button class="btn btn-secondary" id="btn-prev" ${idx === 0 ? 'disabled' : ''}>${icon('chevronLeft')}<span data-i18n="packing.prev">${t('packing.prev')}</span></button>
      <span>${idx + 1} / ${orders.length}</span>
      <button class="btn btn-secondary" id="btn-next" ${idx === orders.length - 1 ? 'disabled' : ''}><span data-i18n="packing.next">${t('packing.next')}</span>${icon('chevronRight')}</button>
    </div>
    <div class="pack-card ${animClass}">
      <button class="btn-icon-red btn-revert-pending" id="btn-revert-pending" data-i18n-title="common.revertTitle" data-i18n-aria="common.revertTitle" aria-label="${esc(t('common.revertTitle'))}" title="${esc(t('common.revertTitle'))}">${icon('revert')}</button>
      <div class="buyer">${esc(order.buyer_name)}</div>
      <div class="address">${esc(order.buyer_address)}</div>
      <div class="allegro-id">
        <span class="allegro-id-label">ID:</span>
        <span class="allegro-id-value">${esc(order.allegro_id)}</span>
        <button class="btn-copy" data-copy="${esc(order.allegro_id)}" data-i18n-title="common.copyId" data-i18n-aria="common.copyId" aria-label="${esc(t('common.copyId'))}" title="${esc(t('common.copyId'))}">${icon('copy', 'icon-copy')}${icon('check', 'icon-check')}</button>
      </div>
      <div class="items">${order.items.map(i => `${i.quantity}x ${esc(i.name)}`).join('<br/>')}</div>
      ${order.tracking_number ? `<div class="tracking-info"><span data-i18n="packing.trackingLabel">${t('packing.trackingLabel')}</span> <strong>${esc(order.tracking_number)}</strong></div>` : ''}
      ${isLocker ? `
      <fieldset class="parcel-sizes" ${pendingSize || order.shipment_id || order.tracking_number ? 'disabled' : ''}>
        <legend data-i18n="packing.lockerLegend">${t('packing.lockerLegend')}</legend>
        <div class="parcel-size-options">
          ${[['A', 'packing.sizeA'], ['B', 'packing.sizeB'], ['C', 'packing.sizeC']].map(([size, key]) => `
            <label class="parcel-size-option">
              <input type="radio" name="parcel-size" value="${size}" ${selectedSize === size ? 'checked' : ''}>
              <span><strong>${size}</strong><span data-i18n="${key}">${t(key)}</span></span>
            </label>`).join('')}
        </div>
      </fieldset>` : `<div class="pack-dims">
        <label data-i18n="packing.dims">${t('packing.dims')}</label>
        <input type="number" class="dim-input" id="dim-l" value="${esc(pkg.length ?? 30)}" min="1"> ×
        <input type="number" class="dim-input" id="dim-w" value="${esc(pkg.width ?? 20)}" min="1"> ×
        <input type="number" class="dim-input" id="dim-h" value="${esc(pkg.height ?? 15)}" min="1">
        <label style="margin-left:12px" data-i18n="packing.weight">${t('packing.weight')}</label>
        <input type="number" class="dim-input" id="dim-wt" value="${esc(pkg.weight ?? 1.0)}" min="0.1" step="0.1">
      </div>`}
      ${lockerNeedsSize ? `<p class="parcel-size-note" data-i18n="packing.selectSizeNote">${t('packing.selectSizeNote')}</p>` : ''}
      <p id="parcel-size-status" class="parcel-size-note" role="status" aria-live="polite">${esc(parcelSizeStatusText(order))}</p>
      <div class="pack-buttons">
        <button class="btn btn-label" id="btn-label" ${lockerNeedsSize || pendingSize ? 'disabled' : ''}>${esc(labelButtonText(isLocker, Boolean(order.shipment_id), false))}</button>
        <button class="btn btn-invoice" id="btn-document">${icon('print')}<span data-i18n="${state.customDocAvailable ? 'packing.customDoc' : 'packing.invoice'}">${t(state.customDocAvailable ? 'packing.customDoc' : 'packing.invoice')}</span></button>
        <button class="btn btn-done" id="btn-done"><span data-i18n="packing.done">${t('packing.done')}</span></button>
      </div>
    </div>
  `;

  view.querySelector('#btn-revert-pending').addEventListener('click', async () => {
    try {
      await api(`/orders/${order.id}/revert-pending`, { method: 'POST' });
    } catch (err) {
      reportError(t('err.revertOrder'), err);
      return;
    }
    await fetchAll();
    state.packingQueue = state.orders.filter(o => o.status === 'packing');
    state.packingIndex = Math.min(state.packingIndex, Math.max(0, state.packingQueue.length - 1));
    renderPackingCard(document.getElementById('content'));
  });

  const copyBtn = view.querySelector('.btn-copy');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(copyBtn.dataset.copy);
        copyBtn.classList.add('copied');
        setTimeout(() => { copyBtn.classList.remove('copied'); }, 1200);
      } catch (err) {
        reportError(t('err.copyId'), err);
      }
    });
  }

  // The label may already exist from an earlier session — do not warn in that case.
  let labelReady = Boolean(order.shipment_id);
  let labelBusy = false;
  const statusEl = view.querySelector('#parcel-size-status');
  if (statusEl) bindDynamicText(statusEl, () => parcelSizeStatusText(order));
  const labelBtn = view.querySelector('#btn-label');
  if (labelBtn) bindDynamicText(labelBtn, () => labelButtonText(isLocker, labelReady, labelBusy));

  view.querySelectorAll('input[name="parcel-size"]').forEach(input => {
    input.addEventListener('change', async () => {
      if (state.parcelSizeSaves.has(order.id)) return;
      const fieldset = view.querySelector('.parcel-sizes');
      const note = view.querySelector('#parcel-size-status');
      state.parcelSizeSaves.set(order.id, { value: input.value });
      state.parcelSizeErrors.delete(order.id);
      fieldset.disabled = true;
      note.textContent = t('packing.savingSize');
      try {
        const result = await api(`/orders/${order.id}/parcel-size`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parcel_size: input.value }),
        });
        for (const saved of [order, ...state.orders, ...state.packingQueue]) {
          if (saved.id === order.id) saved.parcel_size = result.parcel_size;
        }
      } catch (err) {
        state.parcelSizeErrors.set(order.id, { key: 'packing.saveError', vars: { detail: err.message } });
      } finally {
        state.parcelSizeSaves.delete(order.id);
        if (state.currentQueue === 'packing' && state.packingQueue[state.packingIndex]?.id === order.id) {
          renderPackingCard(document.getElementById('content'));
        }
      }
    });
  });

  view.querySelector('#btn-prev').addEventListener('click', () => {
    state.packingDirection = 'prev';
    state.packingIndex--;
    renderPackingCard(document.getElementById('content'));
  });
  view.querySelector('#btn-next').addEventListener('click', () => {
    state.packingDirection = 'next';
    state.packingIndex++;
    renderPackingCard(document.getElementById('content'));
  });
  view.querySelector('#btn-label').addEventListener('click', async () => {
    const btn = view.querySelector('#btn-label');
    const params = isLocker
      ? new URLSearchParams()
      : new URLSearchParams({
        length: view.querySelector('#dim-l').value, width: view.querySelector('#dim-w').value,
        height: view.querySelector('#dim-h').value, weight: view.querySelector('#dim-wt').value,
      });
    btn.disabled = true;
    labelBusy = true;
    btn.textContent = t('packing.generatingLabel');
    try {
      const labelPath = `/print/orders/${order.id}/label`;
      await openPdf(labelPath, {}, () => api(`${labelPath}?${params}`, { method: 'POST' }));
      // Only claim the label is printed once the PDF actually came back.
      labelReady = true;
      labelBusy = false;
      btn.classList.add('printed');
      btn.textContent = labelButtonText(isLocker, true, false);
      try {
        const info = await api(`/print/orders/${order.id}/shipment`);
        if (info && info.shipment_id) {
          order.shipment_id = info.shipment_id;
          if (info.tracking_number) {
            order.tracking_number = info.tracking_number;
            for (const o of [...state.orders, ...state.packingQueue]) {
              if (o.id === order.id) o.tracking_number = info.tracking_number;
            }
          }
        }
      } catch { /* best effort */ }
    } catch (err) {
      labelBusy = false;
      btn.textContent = labelButtonText(isLocker, labelReady, false);
      reportError(t('err.label'), err);
    } finally {
      btn.disabled = false;
    }
  });
  const documentPath = state.customDocAvailable
    ? '/print/custom-doc?order_id=' + encodeURIComponent(order.id)
    : `/print/orders/${order.id}/document`;
  view.querySelector('#btn-document').addEventListener('click', async () => {
    try {
      // One source only: never append the other document in the packing view.
      await openPdf(documentPath);
    } catch (err) {
      reportError(t('err.document'), err);
    }
  });
  view.querySelector('#btn-done').addEventListener('click', async () => {
    if (!labelReady) {
      const ok = confirm(t('packing.doneConfirm'));
      if (!ok) return;
    }
    const card = view.querySelector('.pack-card');
    card.classList.add('animate-done');
    await new Promise(r => setTimeout(r, 430));
    try {
      await api(`/orders/${order.id}/done`, { method: 'POST' });
    } catch (err) {
      reportError(t('err.done'), err);
      renderPackingCard(document.getElementById('content'));
      return;
    }
    await fetchAll();
    state.packingQueue = state.orders.filter(o => o.status === 'packing');
    state.packingIndex = Math.min(state.packingIndex, Math.max(0, state.packingQueue.length - 1));
    state.packingDirection = null;
    renderPackingCard(document.getElementById('content'));
  });
}

// ---- Done view ----

function renderDone(el) {
  const orders = state.orders.filter(o => o.status === 'done');
  el.innerHTML = `<h2 data-i18n="done.title" data-i18n-vars='{"n":${orders.length}}'>${t('done.title', { n: orders.length })}</h2><div class="order-list" id="done-list"></div>`;
  const list = el.querySelector('#done-list');

  if (!orders.length) {
    list.innerHTML = `<p class="empty" data-i18n="done.empty">${t('done.empty')}</p>`;
    return;
  }

  orders.forEach(order => {
    const card = document.createElement('div');
    card.className = 'order-card';
    const labelHtml = order.tracking_number
      ? `<div class="tracking-number">${esc(order.tracking_number)}</div>`
      : order.shipment_id
        ? `<div class="tracking-number"><span data-i18n="done.labelCreated">${t('done.labelCreated')}</span></div>`
        : `<div class="tracking-number missing" data-i18n="done.labelMissing">${t('done.labelMissing')}</div>`;
    card.innerHTML = `
      <div class="order-info">
        <div class="buyer">${esc(order.buyer_name)}</div>
        <div class="address">${esc(order.buyer_address)}</div>
        <div class="allegro-id">
          <span class="allegro-id-label">ID:</span>
          <span class="allegro-id-value">${esc(order.allegro_id)}</span>
          <button class="btn-copy" data-copy="${esc(order.allegro_id)}" data-i18n-title="common.copyId" data-i18n-aria="common.copyId" aria-label="${esc(t('common.copyId'))}" title="${esc(t('common.copyId'))}">${icon('copy', 'icon-copy')}${icon('check', 'icon-check')}</button>
        </div>
        ${labelHtml}
      </div>
      <button class="btn btn-secondary btn-undo" data-id="${order.id}">${icon('revert')}<span data-i18n="done.undo">${t('done.undo')}</span></button>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll('.btn-copy').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        btn.classList.add('copied');
        setTimeout(() => { btn.classList.remove('copied'); }, 1200);
      } catch (err) {
        reportError(t('err.copyId'), err);
      }
    });
  });

  list.querySelectorAll('.btn-undo').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api(`/orders/${btn.dataset.id}/undo-done`, { method: 'POST' });
      } catch (err) {
        reportError(t('err.revertOrder'), err);
        return;
      }
      await fetchAll();
    });
  });
}

// ---- Settings view ----

function renderSettings(el) {
  const activeTab = state.settingsTab;

  el.innerHTML = `
    <h2 data-i18n="settings.title">${t('settings.title')}</h2>
    <div class="settings-tabs">
      <button class="settings-tab ${activeTab === 'documents' ? 'active' : ''}" data-tab="documents" data-i18n="settings.tabDocuments">${t('settings.tabDocuments')}</button>
      <button class="settings-tab ${activeTab === 'shipping'  ? 'active' : ''}" data-tab="shipping" data-i18n="settings.tabShipping">${t('settings.tabShipping')}</button>
      <button class="settings-tab ${activeTab === 'archive'   ? 'active' : ''}" data-tab="archive" data-i18n="settings.tabArchive">${t('settings.tabArchive')}</button>
    </div>
    <div id="settings-panel"></div>
  `;

  el.querySelectorAll('.settings-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      state.settingsTab = btn.dataset.tab;
      renderSettings(el);
    });
  });

  const panel = el.querySelector('#settings-panel');
  if (activeTab === 'documents') renderSettingsDocuments(panel);
  if (activeTab === 'shipping')  renderSettingsShipping(panel);
  if (activeTab === 'archive')   renderSettingsArchive(panel);
}

async function renderSettingsShipping(panel) {
  const s = await api('/print/shipment-settings');
  const sender = s.sender || {};
  const pkg = s.package || {};

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc" data-i18n="settings.shippingIntro">${t('settings.shippingIntro')}</p>
    </div>
    <div class="settings-section">
      <p class="settings-desc" data-i18n-html="settings.defaultPackageHtml">${t('settings.defaultPackageHtml')}</p>
      <div class="settings-field"><label data-i18n="sh.length">${t('sh.length')}</label><input type="number" id="sh-pkg-length" min="1" value="${esc(pkg.length ?? 30)}"></div>
      <div class="settings-field"><label data-i18n="sh.width">${t('sh.width')}</label><input type="number" id="sh-pkg-width" min="1" value="${esc(pkg.width ?? 20)}"></div>
      <div class="settings-field"><label data-i18n="sh.height">${t('sh.height')}</label><input type="number" id="sh-pkg-height" min="1" value="${esc(pkg.height ?? 15)}"></div>
      <div class="settings-field"><label data-i18n="sh.weight">${t('sh.weight')}</label><input type="number" id="sh-pkg-weight" min="0.1" step="0.1" value="${esc(pkg.weight ?? 1.0)}"></div>
      <div class="settings-field"><label data-i18n="sh.pageSize">${t('sh.pageSize')}</label>
        <select id="sh-pkg-page">
          <option value="A6" ${pkg.page_size === 'A6' ? 'selected' : ''}>A6</option>
          <option value="A4" ${pkg.page_size === 'A4' ? 'selected' : ''}>A4</option>
        </select>
      </div>
      <p class="settings-desc" data-i18n="sh.pdfNote">${t('sh.pdfNote')}</p>
    </div>
    <p id="shipping-note" class="settings-note hidden"></p>
    <div class="settings-actions">
      <button class="btn btn-primary" id="shipping-save" data-i18n="common.save">${t('common.save')}</button>
    </div>
  `;

  panel.querySelector('#shipping-save').addEventListener('click', async () => {
    const note = panel.querySelector('#shipping-note');
    const num = (id, fallback) => {
      const value = parseFloat(panel.querySelector(id).value);
      return Number.isFinite(value) ? value : fallback;
    };
    const body = {
      sender, // Preserve legacy settings; shipment addresses now come from Allegro.
      package: {
        type: 'PACKAGE',
        length: num('#sh-pkg-length', 30),
        width: num('#sh-pkg-width', 20),
        height: num('#sh-pkg-height', 15),
        weight: num('#sh-pkg-weight', 1.0),
        label_format: 'PDF',
        page_size: panel.querySelector('#sh-pkg-page').value,
      },
    };
    try {
      await api('/print/shipment-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (err) {
      showNote(note, err.message, 'error');
      return;
    }
    state.shipmentSettings = { sender: body.sender, package: body.package };
    showNote(note, () => t('settings.saved'));
    setTimeout(() => note.classList.add('hidden'), 3000);
  });
}

async function renderSettingsDocuments(panel) {
  const [data, docInfo, docSettings] = await Promise.all([
    api('/print/invoice-settings'),
    api('/print/custom-doc/info'),
    api('/print/document-settings'),
  ]);
  // Keep the packing view's custom-document button in step with the selected source.
  state.customDocAvailable = Boolean(docInfo.available);
  const uploadAvailable = Boolean(docInfo.upload_available ?? docInfo.available);

  async function refreshCustomDocAvailability() {
    try {
      const info = await api('/print/custom-doc/info');
      state.customDocAvailable = Boolean(info && info.available);
    } catch { /* keep the last known value */ }
  }

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc" data-i18n="settings.docsIntro">${t('settings.docsIntro')}</p>
      <div class="settings-checks">
        <label><input type="checkbox" id="inv-buyer-name"    ${(data.show_buyer_name    ?? true) ? 'checked' : ''}> <span data-i18n="inv.buyerName">${t('inv.buyerName')}</span></label>
        <label><input type="checkbox" id="inv-buyer-address" ${(data.show_buyer_address ?? true) ? 'checked' : ''}> <span data-i18n="inv.buyerAddress">${t('inv.buyerAddress')}</span></label>
        <label><input type="checkbox" id="inv-items"         ${(data.show_items         ?? true) ? 'checked' : ''}> <span data-i18n="inv.items">${t('inv.items')}</span></label>
        <label><input type="checkbox" id="inv-price"         ${(data.show_price         ?? true) ? 'checked' : ''}> <span data-i18n="inv.price">${t('inv.price')}</span></label>
        <label><input type="checkbox" id="inv-courier"       ${(data.show_courier       ?? true) ? 'checked' : ''}> <span data-i18n="inv.courier">${t('inv.courier')}</span></label>
        <label><input type="checkbox" id="inv-pickup-point"  ${(data.show_pickup_point  ?? true) ? 'checked' : ''}> <span data-i18n="inv.pickupPoint">${t('inv.pickupPoint')}</span></label>
        <label><input type="checkbox" id="inv-allegro-id"    ${(data.show_allegro_id    ?? true) ? 'checked' : ''}> <span data-i18n="inv.allegroId">${t('inv.allegroId')}</span></label>
      </div>
      <div class="settings-field">
        <label data-i18n="inv.freeTextLabel">${t('inv.freeTextLabel')}</label>
        <textarea id="inv-free-text" rows="2" maxlength="160" data-i18n-placeholder="inv.freeTextPlaceholder" placeholder="${esc(t('inv.freeTextPlaceholder'))}">${esc(data.free_text || '')}</textarea>
        <span id="inv-free-text-count" class="settings-char-count">${(data.free_text || '').length} / 160</span>
      </div>
      <p id="invoice-settings-note" class="settings-note hidden"></p>
      <div class="settings-actions">
        <button class="btn btn-primary" id="invoice-settings-save" data-i18n="common.save">${t('common.save')}</button>
      </div>
    </div>

    <div class="settings-section">
      <a class="btn btn-secondary" id="open-document-editor" href="#document-editor-card" data-i18n="settings.openDocumentEditor">${t('settings.openDocumentEditor')}</a>
    </div>

    <div class="settings-section">
      <p class="settings-desc" data-i18n="settings.customDocDesc">${t('settings.customDocDesc')}</p>
      <div class="custom-doc-status ${uploadAvailable ? 'available' : 'empty'}" id="custom-doc-status">
        ${uploadAvailable
          ? `<span data-i18n="settings.docUploaded">${t('settings.docUploaded')}</span><button class="btn btn-secondary btn-sm" id="btn-doc-delete" data-i18n="common.delete">${t('common.delete')}</button>`
          : `<span class="dim" data-i18n="settings.docNone">${t('settings.docNone')}</span>`
        }
      </div>
      <div class="settings-field upload-field">
        <input type="file" id="custom-doc-file" accept=".pdf" class="hidden">
        <button class="btn btn-secondary" id="btn-doc-pick">${uploadAvailable ? esc(t('settings.docReplace')) : esc(t('settings.docChoose'))}</button>
        <span id="custom-doc-filename" class="dim doc-file-name"></span>
      </div>
      <p id="custom-doc-note" class="settings-note hidden"></p>
    </div>
    <section class="settings-section settings-editor-card" id="document-editor-card" aria-labelledby="document-editor-title" tabindex="-1">
      <h3 id="document-editor-title" data-i18n="settings.documentEditor">${t('settings.documentEditor')}</h3>
      <p class="settings-desc" data-i18n="settings.documentEditorDesc">${t('settings.documentEditorDesc')}</p>
      <div id="document-editor"></div>
    </section>
  `;

  panel.querySelector('#open-document-editor').addEventListener('click', event => {
    event.preventDefault();
    const card = panel.querySelector('#document-editor-card');
    card.focus({ preventScroll: true });
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  panel.querySelector('#btn-doc-pick').setAttribute('data-i18n', uploadAvailable ? 'settings.docReplace' : 'settings.docChoose');

  panel.querySelector('#inv-free-text').addEventListener('input', function() {
    panel.querySelector('#inv-free-text-count').textContent = `${this.value.length} / 160`;
  });

  panel.querySelector('#invoice-settings-save').addEventListener('click', async () => {
    const body = {
      show_buyer_name:    panel.querySelector('#inv-buyer-name').checked,
      show_buyer_address: panel.querySelector('#inv-buyer-address').checked,
      show_items:         panel.querySelector('#inv-items').checked,
      show_price:         panel.querySelector('#inv-price').checked,
      show_courier:       panel.querySelector('#inv-courier').checked,
      show_pickup_point:  panel.querySelector('#inv-pickup-point').checked,
      show_allegro_id:    panel.querySelector('#inv-allegro-id').checked,
      free_text:          panel.querySelector('#inv-free-text').value,
    };
    const note = panel.querySelector('#invoice-settings-note');
    try {
      await api('/print/invoice-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      showNote(note, () => t('settings.saved'));
    } catch (err) {
      showNote(note, err.message, 'error');
    }
  });

  // Custom doc — file picker
  const fileInput = panel.querySelector('#custom-doc-file');
  panel.querySelector('#btn-doc-pick').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;
    panel.querySelector('#custom-doc-filename').textContent = file.name;
    const form = new FormData();
    form.append('file', file);
    const note = panel.querySelector('#custom-doc-note');
    let res;
    try {
      res = await apiFetch('/print/custom-doc', { method: 'POST', body: form });
    } catch (err) {
      showNote(note, err.message, 'error');
      return;
    }
    if (res.ok) {
      await refreshCustomDocAvailability();
      showNote(note, () => t('settings.docUploadedOk'));
      panel.querySelector('#custom-doc-status').outerHTML =
        `<div class="custom-doc-status available" id="custom-doc-status"><span data-i18n="settings.docUploaded">${t('settings.docUploaded')}</span><button class="btn btn-secondary btn-sm" id="btn-doc-delete" data-i18n="common.delete">${t('common.delete')}</button></div>`;
      setText(panel.querySelector('#btn-doc-pick'), 'settings.docReplace');
      attachDeleteHandler(panel);
    } else {
      const err = await responseError(res);
      showNote(note, err.message, 'error');
    }
  });

  function attachDeleteHandler(p) {
    const btn = p.querySelector('#btn-doc-delete');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      try {
        await api('/print/custom-doc', { method: 'DELETE' });
      } catch (err) {
        reportError(t('err.docDelete'), err);
        return;
      }
      await refreshCustomDocAvailability();
      p.querySelector('#custom-doc-status').outerHTML =
        `<div class="custom-doc-status empty" id="custom-doc-status"><span class="dim" data-i18n="settings.docNone">${t('settings.docNone')}</span></div>`;
      setText(p.querySelector('#btn-doc-pick'), 'settings.docChoose');
      p.querySelector('#custom-doc-filename').textContent = '';
      attachDeleteHandler(p);
    });
  }
  attachDeleteHandler(panel);

  // Mount once in the full-width card, outside the narrow invoice/upload controls.
  if (typeof DocumentEditor !== 'undefined') {
    DocumentEditor.mount(panel.querySelector('#document-editor'), {
      settings: docSettings,
      orders: state.orders,
      onSaved: refreshCustomDocAvailability,
    });
  }
}

async function renderSettingsArchive(panel) {
  const entries = await api('/orders/archive');

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc" ${entries.length
        ? `data-i18n="settings.archiveCount" data-i18n-count="${entries.length}" data-i18n-vars='{"n":${entries.length}}'`
        : 'data-i18n="settings.archiveEmpty"'}>${entries.length ? t('settings.archiveCount', { n: entries.length }, entries.length) : t('settings.archiveEmpty')}</p>
      ${entries.length ? `<div class="archive-list">${entries.map(e => `<div class="archive-item">
        <span>${esc(e.allegro_id)}</span>
        <span class="dim" data-archived-at="${esc(e.archived_at || '')}"></span>
      </div>`).join('')}</div>` : ''}
    </div>
  `;

  panel.querySelectorAll('[data-archived-at]').forEach(node => {
    const value = node.getAttribute('data-archived-at');
    bindDynamicText(node, () => (value ? formatDateTime(value) : t('settings.archiveNoDate')));
  });
}

// ---- Sidebar events ----

document.querySelectorAll('.queue-item').forEach(el => {
  el.addEventListener('click', () => renderQueue(el.dataset.queue));
});

document.getElementById('btn-settings').addEventListener('click', () => renderQueue('settings'));

function initLanguageControls() {
  applyDocumentLanguage();
  document.querySelectorAll('[data-lang-select]').forEach(select => {
    select.addEventListener('change', () => setLanguage(select.value));
  });
  syncLanguageControls(document);
  applyLanguage(document);
}

document.getElementById('btn-zakoncz').addEventListener('click', async () => {
  if (!confirm(t('day.confirm'))) return;
  const doneOrders = state.orders.filter(o => o.status === 'done');
  if (!doneOrders.length) {
    showToast(() => t('day.noneReady'));
    return;
  }
  const missing = doneOrders.filter(o => !o.shipment_id && !o.tracking_number);
  if (missing.length) {
    const ok = confirm(t('day.missingLabels', { n: missing.length }, missing.length));
    if (!ok) return;
  }
  try {
    await api('/orders/zakoncz-dzien', { method: 'POST' });
  } catch (err) {
    reportError(t('err.endDay'), err);
    return;
  }
  await fetchAll();
  if (state.currentQueue === 'settings') renderQueue('settings');
});

document.getElementById('btn-sync').addEventListener('click', async () => {
  const btn = document.getElementById('btn-sync');
  btn.disabled = true;
  try {
    await api('/orders/sync', { method: 'POST' });
  } catch (err) {
    reportError(t('err.sync'), err);
    return;
  } finally {
    btn.disabled = false;
  }
  await fetchAll();
});

document.getElementById('btn-auth').addEventListener('click', async () => {
  try {
    const data = await api('/orders/auth/url');
    window.location.href = data.url;
  } catch (e) {
    reportError(t('common.errorPrefix'), e);
  }
});


// ---- Auto-refresh pending every 60s ----
setInterval(() => {
  if (appReady && state.currentQueue === 'pending') fetchAll();
}, 60000);

// ---- Auth status ----

async function checkAuthStatus() {
  try {
    const data = await api('/orders/auth/status');
    const button = document.getElementById('btn-auth');
    button.style.display = 'block';
    state.authorized = Boolean(data.authorized);
    setText(button, data.authorized ? 'nav.reconnectAllegro' : 'nav.authorizeAllegro');
  } catch {}
}

// ---- Custom doc availability ----

async function checkCustomDoc() {
  try {
    const data = await api('/print/custom-doc/info');
    state.customDocAvailable = data.available;
  } catch {}
}

// ---- Boot ----

async function startApp() {
  document.getElementById('setup').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  appReady = true;
  await Promise.all([fetchAll(), checkAuthStatus(), checkCustomDoc()]);
}

function setupMessage(content, isError = false) {
  const el = document.getElementById('setup-message');
  if (!el) return;
  el.classList.toggle('error', isError);
  if (typeof content === 'function') {
    el.removeAttribute('data-i18n');
    bindStaticText(el, content);
    return;
  }
  // A raw message (usually an upstream error) has no catalog key: detach it so a
  // language switch never overwrites it with unrelated catalog text.
  clearStaticText(el);
  el.removeAttribute('data-i18n');
  el.textContent = content || '';
}

async function boot() {
  const retry = document.getElementById('setup-retry');
  retry.classList.add('hidden');
  setupMessage(() => t('setup.checking'));
  try {
    const status = await api('/setup/status');
    if (status.configured) {
      await startApp();
      return;
    }
    const form = document.getElementById('setup-form');
    setText(document.getElementById('setup-environment'),
      status.sandbox ? 'setup.envSandbox' : 'setup.envProduction');
    document.getElementById('setup-redirect-uri').textContent = status.redirect_uri;
    form.classList.remove('hidden');
    setupMessage('');
    form.onsubmit = async event => {
      event.preventDefault();
      const submit = document.getElementById('setup-submit');
      const clientId = document.getElementById('setup-client-id');
      const clientSecret = document.getElementById('setup-client-secret');
      submit.disabled = true;
      setText(submit, 'setup.saving');
      setupMessage('');
      try {
        // Existing installations keep their current operator authentication.
        if (status.requires_access_token) await promptForAccessToken();
        const result = await api('/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Packing-Setup-Token': status.setup_token },
          body: JSON.stringify({ client_id: clientId.value.trim(), client_secret: clientSecret.value.trim() }),
        });
        clientId.value = '';
        clientSecret.value = '';
        form.classList.add('hidden');
        retry.classList.add('hidden');
        if (result.access_token) {
          setAccessToken(result.access_token);
          document.getElementById('setup-access-token').value = result.access_token;
          document.getElementById('setup-success').classList.remove('hidden');
          setupMessage(() => t('setup.savedMsg'));
          document.getElementById('setup-access-token').focus();
        } else {
          await startApp();
        }
      } catch (err) {
        setupMessage(err.message ? err.message : () => t('setup.saveFailed'), true);
        retry.classList.remove('hidden');
      } finally {
        submit.disabled = false;
        setText(submit, 'setup.submit');
      }
    };
    document.getElementById('setup-client-id').focus();
  } catch (err) {
    setupMessage(err.message ? err.message : () => t('setup.statusFailed'), true);
    retry.classList.remove('hidden');
  }
}

document.getElementById('setup-retry').addEventListener('click', boot);
document.getElementById('setup-continue').addEventListener('click', async () => {
  document.getElementById('setup-access-token').value = '';
  await startApp();
});
document.getElementById('setup-copy-token').addEventListener('click', async () => {
  const field = document.getElementById('setup-access-token');
  try {
    await navigator.clipboard.writeText(field.value);
    setupMessage(() => t('setup.tokenCopied'));
  } catch {
    field.focus();
    field.select();
    setupMessage(() => t('setup.tokenCopyManual'));
  }
});

initLanguageControls();
boot();

// Check every 30s in case user just came back from Allegro auth page
setInterval(() => { if (appReady) checkAuthStatus(); }, 30000);
