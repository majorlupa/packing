# Weles

Docker-based order-packing application integrating Allegro order management and shipment labels.

## Technology

- Backend: Python/FastAPI
- Frontend: static HTML, CSS, and JavaScript
- Persistence: JSON state file in `data/state.json`
- Documents: WeasyPrint and pypdf
- Deployment: one Docker Compose service exposing port 3001

## Development and deployment

Build and start the application with:

```sh
docker compose build packing
docker compose up -d
```

The Compose service mounts `./data` for persistent state, loads credentials from the host
`.env` through `env_file`, and binds port 3001 to localhost. Keep `.env` mode 0600 and out
of version control; `.dockerignore` keeps it and `data/` out of the build context.
Set `PACKING_ACCESS_TOKEN` to a random value of at least 32 characters (see `.env.example`).
The browser asks for that token when opening the app and holds it only for the page session.

The FastAPI application serves the frontend at `/`, static assets at `/static`, and API routes below `/api`.

## Tests

```sh
python -m pytest backend/tests -q
```

Needs `backend/requirements-dev.txt` (pytest). The suite covers the queue workflow, the
state-file durability rules below, the request contracts, and the shipment-label edge cases.
It runs against a temporary data directory and never calls Allegro.

## Persistence rules

`backend/store.py` owns all state access, and the rules there are load-bearing:

- Every write is a temp file + fsync + `os.replace()`; the previous generation stays in
  `data/state.json.bak`, which is also the fallback when `state.json` is unreadable. A broken
  file is moved to `state.json.corrupt-<timestamp>`, never overwritten.
- An unreadable state file makes the API answer `503` with the reason (and `/health` reports
  `degraded`) instead of a bare 500 per request; the UI shows it as a banner.
- Records that fail validation are quarantined (kept in the file, reported by
  `/api/orders/status`) so one bad record cannot take the whole queue down.
- Keep `.env` on the host and pass it to the container with Compose `env_file`; do not expose
  it through an application endpoint. The API requires `PACKING_ACCESS_TOKEN` for all routes
  under `/api/`, and Compose binds the web port to localhost.

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
- Shipment HTTP contract tests: `python -m pytest backend/tests/test_allegro_shipments.py -q`.
  Browser print-flow tests: `node --test frontend/tests/print.test.cjs`.
- `backend/api/inpost_shipx.py` is retained for reference but is not used by the current label flow.
- The OAuth callback targets `http://localhost:3001/api/orders/auth/callback` by default; override
  with `ALLEGRO_REDIRECT_URI` and `PACKING_BASE_URL` (see `.env.example`).
- Allegro client failures map to 401 (not authorized) or 502 (upstream), never 404.

See `FINDINGS.md` for the latest review, deployment notes, and API audit.
