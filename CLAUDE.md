# Weles

Docker-based order-packing application integrating Allegro order management and shipment labels.

## Technology

- Backend: Python/FastAPI
- Frontend: static HTML, CSS, and JavaScript
- Persistence: JSON state file in `data/state.json`
- Documents: WeasyPrint and pypdf
- Deployment: one Docker Compose service exposing port 3001

## Development and deployment

For a new installation, create an empty configuration from the example first:

```sh
cp .env.example .env
chmod 600 .env
```

Build and start the application with:

```sh
docker compose build packing
docker compose up -d
```

Open `http://localhost:3001`. If either Allegro credential is missing, first-run onboarding
asks for Client ID and Client Secret. It shows the configured sandbox/production environment
and the redirect URI to register in Allegro. Saving writes only those keys to the host `.env`,
preserves the other settings, and applies the credentials immediately. Then use
"Autoryzuj Allegro" to connect the seller account through OAuth.

If no valid `PACKING_ACCESS_TOKEN` exists, setup generates one, saves it in `.env`, and
shows it once. Save this token for future visits. If a token was already configured, setup
requires it before saving. The browser holds the token only for the page session and asks
for it on subsequent visits. Existing installations with both Allegro credentials skip onboarding.

The Compose service mounts `./data` for persistent state and the host `.env` at `/app/.env`,
loads initial settings through `env_file`, and binds port 3001 to localhost. The mounted file
is authoritative for the three setup keys on startup, including after a container restart.
Other settings retain Compose's resolved environment values. Keep `.env` mode 0600 and
out of version control; `.dockerignore` keeps it and `data/` out of the build context.
The file must exist and be writable by the container's uid 1000. Local development also
loads the project `.env`; override its path with `PACKING_ENV_FILE`.

The FastAPI application serves the frontend at `/`, static assets at `/static`, and API routes below `/api`.

## Tests

```sh
python -m pytest backend/tests -q
```

Needs `backend/requirements-dev.txt` (pytest). The suite covers the queue workflow, the
state-file durability rules below, the request contracts, and the shipment-label edge cases.
It runs against a temporary data directory and never calls Allegro. First-run tests additionally
cover secret-safe validation, access control, preserving a Docker bind mount's inode,
unrelated settings, and loading saved credentials after restart.

## Persistence rules

`backend/store.py` owns all state access, and the rules there are load-bearing:

- Every write is a temp file + fsync + `os.replace()`; the previous generation stays in
  `data/state.json.bak`, which is also the fallback when `state.json` is unreadable. A broken
  file is moved to `state.json.corrupt-<timestamp>`, never overwritten.
- An unreadable state file makes the API answer `503` with the reason (and `/health` reports
  `degraded`) instead of a bare 500 per request; the UI shows it as a banner.
- Records that fail validation are quarantined (kept in the file, reported by
  `/api/orders/status`) so one bad record cannot take the whole queue down.
- Keep `.env` on the host; the application never returns its contents or Allegro credentials.
  Setup updates the mounted file in place under a file lock with fsync (renaming a bind-mounted
  file would fail). This is separate from the atomic state-file persistence described above.
  The API requires `PACKING_ACCESS_TOKEN` for routes under `/api/`, except the OAuth callback,
  credential-free setup status, and first-run setup when no valid token exists. Setup requires
  the exact browser origin and a setup nonce, bootstrap is limited to localhost, and existing
  Allegro credentials cannot be overwritten. Compose binds the web port to localhost.

## Application workflow

Orders move through four queues:

1. Pending orders are synchronized from Allegro.
2. Selected orders are grouped into picking lists.
3. Picking lists move orders into the packing queue.
4. Packed orders are marked done and can be archived.

The packing view can request an Allegro shipment label and generate a combined sales/custom document PDF.

Label creation is serialised per order (`routes/print_routes.py`): a shipment costs money and
may only be created once, so a double click must not create two.

## Integration notes

- Allegro access and refresh tokens are persisted to `data/allegro_token.json` (mode 0600).
  A restart preserves the session, but invalidates any unfinished OAuth authorization flow.

- Allegro uses OAuth2 authorization-code flow.
- Shipment labels use Allegro Shipment Management. Sender/recipient addresses, pickup points,
  COD and insurance come from `GET /shipment-management/delivery-proposals/{orderId}`.
  Set the sender address in Allegro's address book; legacy local sender settings are ignored.
  The packing view controls parcel dimensions/weight. New labels are always PDF; A4/A6 is
  applied at download time. Existing shipment IDs are reused on subsequent print attempts.
- `PACKING_SHIPMENT_DRY_RUN=true` exercises the whole label flow without calling Allegro:
  `create_shipment` returns a `dry-run-…` id and `download_label` a blank PDF. Intended for the
  beta instance; never enable it in production.
  This is also the only switch that lets fabricated data into the app: `POST /api/orders/seed-mock`
  answers 409 without it, and `/api/orders/sync` falls back to sample orders only when Allegro is
  genuinely unauthorized — every other upstream failure surfaces as 401/502 rather than
  silently filling the queue with records that cannot be shipped.
  `GET /api/orders/status` reports the flag as `dry_run` so the browser can hide the
  sample-orders button instead of offering an action the API rejects.
- Shipment HTTP contract tests: `python -m pytest backend/tests/test_allegro_shipments.py -q`.
  Browser print-flow tests: `node --test frontend/tests/print.test.cjs`.
- `backend/api/inpost_shipx.py` is retained for reference but is not used by the current label flow.
- The OAuth callback targets `http://localhost:3001/api/orders/auth/callback` by default; override
  with `ALLEGRO_REDIRECT_URI` and `PACKING_BASE_URL` (see `.env.example`).
- Allegro client failures map to 401 (not authorized) or 502 (upstream), never 404.

See `FINDINGS.md` for the latest review, deployment notes, and API audit.

## Beta: Paczkomat InPost parcel sizes

Delivery method names containing both `InPost` and `Paczkomat` (including
`Allegro Paczkomaty InPost`) appear under `Paczkomat InPost` in pending orders.
Their packing cards offer A/B/C instead of dimensions and weight. The optional
`parcel_size` order field is saved atomically through
`PATCH /api/orders/{id}/parcel-size` and survives restarts and queue changes.
New locker orders have no size selected; choosing A, B, or C explicitly saves it.
Pending saves retain their selection and disable further changes across navigation.
Courier deliveries retain dimension/weight inputs.

Carrier integration for these size choices maps gabaryty to standard locker dimensions:
- Gabaryt A: 64 × 38 × 8 cm
- Gabaryt B: 64 × 38 × 19 cm
- Gabaryt C: 64 × 38 × 41 cm
Label creation submits these dimensions to Allegro Shipment Management (`/shipment-management/shipments/create-commands`),
fetches the tracking number, and downloads the PDF label. Allegro returns two identifiers:
`packages[].waybill` is its own, while the carrier number usable in carrier tracking is
`packages[].transportingInfo[].carrierWaybill`, which can be an empty string on the first
read after creation — so the carrier number is preferred and `waybill` is the fallback.
A shipment whose number was missing is recovered from Allegro on the next label print or
via `GET /print/orders/{id}/shipment`.
Selecting a size enables the label button in the packing view.

Offline testing: with `PACKING_SHIPMENT_DRY_RUN=true`, `POST /api/orders/seed-mock`
plants three realistic mock orders (two Paczkomat InPost, one courier) so the whole
workflow can be tested end-to-end with simulated labels and tracking codes. Sync falls
back to those orders only when Allegro is not authorized at all; a working session is
never overridden by mock data.
