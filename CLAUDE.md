# Packing App

Docker-based order packing tool for Polish micro-businesses using Allegro + multi-courier shipping.

## What this is

Streamlines the packing workflow: pulling Allegro orders, generating courier labels, printing invoices. Real daily pain at work — boss is the first user. Open source / portfolio project.

## Tech stack

- **Backend:** Python FastAPI
- **Frontend:** Simple HTML/JS
- **Infrastructure:** Docker + docker-compose (part of `/home/tomek/exodia/docker-compose.yaml`)
  - Services: `packing-backend`, `packing-frontend` (port 3001)
  - Run without sudo — tomek is in docker group (needs re-login)
- **State:** persisted in `/home/tomek/Projects/packing/data/state.json`
- **Secrets:** `.env` file, never committed

## APIs

- **Allegro OAuth2** — Authorization Code flow, redirect to `http://localhost:3001/api/orders/auth/callback`
- **Allegro Shipment Management** — unified label fetching for ALL couriers
  - `GET /shipment-management/shipments?checkoutFormId=X` — find shipment (Accept: `application/vnd.allegro.public.v2+json`)
  - `GET /shipment-management/shipments/{id}/label` — download PDF label
- **InPost ShipX** — file exists (`api/inpost_shipx.py`) but unused, labels come from Allegro

## Couriers

All of them (InPost paczkomat, InPost kurier, DPD, DHL, etc.). Labels are created in Allegro's system, app downloads them via Allegro's shipment management API — no per-carrier integration needed.

## Workflow (4 queues in left sidebar)

1. **Oczekujące (Pending)** — incoming Allegro orders; user builds picking lists as consolidated batches; printable A4 picking list
2. **Kompletowanie (Picking)** — active picking lists; rename inline, print A4, send to Packing, or revert to Pending
3. **Pakowanie (Packing)** — carousel of individual orders in a batch; each card shows buyer + items; two print buttons: Zebra 10x15cm label (PDF from Allegro) + A4 invoice; GOTOWE → Done
4. **Gotowe (Done)** — archive with undo

## Printers

- **Zebra** label printer — 10x15cm courier stickers (PDF from Allegro API)
- **A4** regular printer — buyer invoices (HTML rendered in browser)

## Current status (2026-03-23)

- Allegro sandbox connected, two test sales created
- Label endpoint rewritten to use Allegro Shipment Management API (v2 Accept header fix applied)
- Needs rebuild + end-to-end label print test

## Next steps

- Re-login so docker group takes effect (no more sudo needed)
- Rebuild packing-backend, test label printing with sandbox orders
- Test with real Zebra + A4 in production
- Connect production Allegro account

## Working style

- Keep scope tight — one thing at a time
- Celebrate small wins
- No complexity beyond what's asked
