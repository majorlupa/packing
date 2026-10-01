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

The Compose service mounts `./data` for persistent state and `./.env` for credentials. Keep credentials out of version control. `.dockerignore` keeps both out of the build context.

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
- Do not rename-replace `/app/.env`: it is bind-mounted as a single file, so `os.replace()`
  fails with `EBUSY`. `routes/config.py` writes it in place for that reason.
- Allegro OAuth tokens are persisted to `data/allegro_token.json` (mode 0600) together with
  the access-token expiry, and refreshed automatically, so a container restart does not require
  re-authorizing.

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

- Allegro uses OAuth2 authorization-code flow.
- Shipment labels use Allegro Shipment Management.
- `backend/api/inpost_shipx.py` is retained for reference but is not used by the current label flow.
- The OAuth callback targets `http://localhost:3001/api/orders/auth/callback` by default; override
  with `ALLEGRO_REDIRECT_URI` and `PACKING_BASE_URL` (see `.env.example`).
- Allegro client failures map to 401 (not authorized) or 502 (upstream), never 404.

See `FINDINGS.md` for the latest review, deployment notes, and API audit.
