# Weles

Self-hosted order packing desk for Allegro sellers. One Docker service replaces
the spreadsheet-and-printer routine: orders are synced from Allegro, batched into
picking lists, packed, and finished with a real shipment label and a combined
sales/custom document PDF.

No SaaS, no per-seat fees — your orders stay on your machine and only talk to Allegro's API.

> **Status: work in progress.** The code runs, but it is **not finished**. Label
> creation, order sync and document generation are still being verified against the
> Allegro **sandbox**, which the author does not have working yet — so treat every
> part of the queue workflow as unproven until that lands. Shipping labels cost real
> money, and there is no production-readiness guarantee. Use it to look around, not to
> run your shop. Issues and pull requests welcome.

## What it does

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

## Requirements

- Docker with Compose
- Allegro developer app (`https://developer.allegro.pl`) with Client ID and Client Secret

## Quick start

```sh
git clone https://github.com/majorlupa/packing.git
cd packing
cp .env.example .env
chmod 600 .env
docker compose build packing
docker compose up -d
```

Open <http://localhost:3001>.

First run walks you through the rest:

1. Enter the Allegro Client ID and Client Secret. They are written to `.env` on the host
   and applied immediately.
2. Use **Autoryzuj Allegro** to connect the seller account (OAuth2, redirect URI
   `http://localhost:3001/api/orders/auth/callback` – register it in your Allegro app).
3. Setup generates a `PACKING_ACCESS_TOKEN`, shows it once, and saves it. Keep it: your
   browser asks for it on later visits.

Labels cost money, and the Allegro sandbox is frequently unavailable or tricky to set up.
Use `PACKING_SHIPMENT_DRY_RUN=true` to exercise the entire application flow (order sync with realistic
mock orders, picking lists, Paczkomat InPost gabaryt A/B/C selection, shipment creation, tracking numbers,
and blank PDF labels) without needing a live Allegro connection. Never enable dry run in production.

In dry run the pending view also offers **Wczytaj zamówienia testowe**, which plants three
sample orders so the workflow can be walked through with an empty queue. That button and
its endpoint `POST /api/orders/seed-mock` exist only in dry run: the API answers 409
otherwise, because those orders carry invented Allegro ids that cannot be shipped and
would sit in a real queue looking like paid ones.

## Configuration

Everything lives in `.env`; the only required keys are the Allegro credentials and the
access token. See [`.env.example`](.env.example) for the optional ones
(sandbox toggle, redirect URI, extra CORS origins, dry run).

The Compose service mounts `./data` for state and the host `.env` inside the container,
so the file stays the single source of truth across restarts and updates. Keep it mode
`0600` and out of version control. The web port is bound to localhost only.

## Development

```sh
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
PACKING_ENV_FILE=.env python -m pytest backend/tests -q      # never calls Allegro
```

`CLAUDE.md` documents the architecture, persistence rules, and integration notes in
detail.

## Disclaimer

This is an independent, unfinished tool, not affiliated with or endorsed by Allegro.
Back up `data/`, keep `PACKING_SHIPMENT_DRY_RUN=true` while testing, and verify a
label before handing a parcel to the courier.