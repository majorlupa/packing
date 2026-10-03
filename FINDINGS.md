# Project findings

> The high/medium items below marked as fixed were addressed in the 2026-09-21 pass —
> see "Fixed since this review" at the end. Everything unmarked is still open.

## Overview

The application is a FastAPI backend with a static HTML/JavaScript frontend. It synchronizes Allegro orders, groups them into picking lists, supports a packing carousel, creates Allegro shipment labels, renders invoices, and archives completed orders.

State is stored in `data/state.json`; uploaded custom documents are stored in the same data volume.

## Container consolidation

The previous deployment used an Nginx frontend container and a FastAPI backend container. It is now consolidated into one `packing` service:

- `Dockerfile` builds Python dependencies and copies both backend and frontend.
- FastAPI serves `/` and `/static` directly.
- The API is mounted at `/api`, preserving the existing frontend URLs.
- `docker-compose.yaml` binds port 3001 to localhost, loads `.env` with Compose `env_file`,
  and mounts the data directory plus a writable `.env` for first-run setup.

The image was built successfully and smoke-tested for `/`, `/health`, and `/api/orders/`.

The old `frontend/Dockerfile` and `frontend/nginx.conf` remain as legacy files but are no longer used by Compose.

## Code review findings

### High priority

- **Fixed (2026-10-01):** Removed the Allegro token-return, raw-order debug, and unrestricted `.env` read/write endpoints. First-run onboarding now has a narrow write-only endpoint for Allegro credentials; no endpoint returns `.env` or those credentials.
- **Fixed (2026-10-01):** `/api/` routes require `PACKING_ACCESS_TOKEN`; the OAuth callback validates a one-time `state` value. Public setup status contains no credentials. One-time setup is allowed without bearer authentication only when credentials and a valid access token are missing, with localhost, exact-origin, and nonce checks; it generates an access token. Existing tokens are required before saving.
- **Fixed (2026-10-01):** Compose binds port 3001 to localhost. `.env` is now mounted writable for setup, with mode 0600 and updates limited to the setup keys. Existing configurations cannot be overwritten through onboarding.

### Medium priority

- OAuth tokens are held only in process memory. Restarting the container loses authorization; there is no refresh-token or expiry handling. **Still open.**
- OAuth callback remains configurable; one-time `state` validation is now enabled. **PKCE is still missing.**
- Synchronization requests at most 100 `READY_FOR_PROCESSING` orders and does not use Allegro event cursors or pagination, so orders can be missed. **Still open.**
- Allegro requests have no retry/backoff strategy. **Still open** (timeouts and error classes were added).
- `tracking_number` is displayed by the UI but is never populated by the current sync flow. **Still open** — the UI no longer keys its "no label" warning on it.
- JSON read/modify/write operations have no locking or transaction protection; concurrent requests can overwrite state. **Fixed** (single lock, one write per operation).
- CORS is configured with `allow_origins=["*"]`. **Fixed** (`PACKING_CORS_ORIGINS`, defaults to the local UI origins).

### Correctness and maintainability

- The Allegro client comment says “device authorization flow,” while the implementation is authorization-code OAuth. **Fixed** (comment corrected).
- Frontend calls generally do not check HTTP errors before updating UI state. **Fixed** (all calls go through one helper; failures alert).
- Several frontend templates interpolate API data directly into `innerHTML`; escaping should be added for external values. **Fixed** (escaped before interpolation).

## Allegro API audit

The endpoint families documented in `api.md` remain broadly valid: order events, event statistics, checkout forms, checkout-form details, and shipment management.

Current documentation adds `codBookedPayments[]` to checkout-form responses. The shipment-management delivery-services endpoint is deprecated, with delivery proposals recommended for new integrations. Recent Pocztex changes removed pickup-related proposal fields; the current client does not send those fields and is unaffected.

The current code correctly uses the Allegro auth host for token exchange and the API host for order/shipment calls. It uses bearer authentication and Allegro media types.

Official references:

- [Allegro order management](https://developer.allegro.pl/tutorials/jak-obslugiwac-zamowienia-GRaj0qyvwtR)
- [Allegro OAuth authentication](https://developer.allegro.pl/tutorials/uwierzytelnianie-i-autoryzacja-zlq9e75GdIR)
- [COD payment details changelog](https://developer.allegro.pl/news/zarzadzanie-zamowieniami-dodalismy-szczegoly-platnosci-pobraniowych-GRnx7KnBeFr)

## Recommended next steps

1. Rotate any Allegro and InPost credentials that may have been exposed while the old API was reachable. **Operator action required in the provider dashboards.**
2. Persist encrypted OAuth credentials with refresh and expiry handling. **Still open.**
3. Replace 100-item polling with event-based incremental synchronization and pagination. **Still open.**
4. Add request retries, timeouts, and structured Allegro error handling. **Partly done:** timeouts, typed errors and correct status codes; no retries yet.
5. Implement tracking-number synchronization. **Still open.**
6. Add tests for state transitions, concurrent writes, and API response-shape changes. **Done:** `backend/tests/test_api.py` (35 tests).

## Fixed since this review (2026-09-21)

Verified by building the image, running the container and driving the API end-to-end; see
`backend/tests/` for the regression tests.

1. **The state file can no longer take the queue down.** `backend/store.py` writes through a
   temp file + `os.replace()` and keeps `state.json.bak`; a file that cannot be parsed is
   preserved as `state.json.corrupt-<timestamp>` and the API answers 503 (with the reason on
   `/health` and in a UI banner) instead of 500-ing every request. Records that fail validation
   are quarantined and reported by `/api/orders/status`, dangling picking-list references are
   repaired, and archive entries were migrated from bare ids to `{allegro_id, archived_at}`.
   Measured: 13 legacy orders and the old archive loaded unchanged in the running container.
2. **A label can no longer be created twice.** `GET /api/print/orders/{id}/label` is serialised
   per order, so two parallel requests create one shipment (regression test asserts one
   `create_shipment` call).
3. **Settings endpoints are typed.** `POST /api/print/shipment-settings` takes a validated model;
   garbage is now 422 and the Wysyłka tab stays readable (previously it 500-ed forever after one
   bad write).
4. **Request contracts fixed.** Renaming a picking list needs only `name`; creating one requires
   at least one order id; upstream failures are 401/502 instead of 404; `free_text` is bounded
   at 160 chars; uploads must be real PDFs under 20 MB.
5. **State writes are transactional.** One lock plus one write per operation (sync, archive,
   bulk status changes), which also removes the lost-update window on concurrent requests.
6. **Deployment is reproducible.** `docker-compose.yaml`, `CLAUDE.md` and the API reference docs
   are no longer gitignored; `.dockerignore` was added so `.env` and `data/` stay out of the build
   context; the image runs as uid 1000 (so `./data` stays operator-owned) and has a healthcheck;
   `backend/Dockerfile` is documented as the dev variant.
7. **Frontend honesty.** Every API call goes through one helper that surfaces failures instead of
   silently re-rendering; the label button only reports success after the PDF arrives; API values
   are escaped before they reach `innerHTML`; the packing view seeds its dimensions from the
   shipping settings, which are now editable and actually used.
