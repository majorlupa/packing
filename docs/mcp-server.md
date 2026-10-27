# MCP server

An [MCP](https://modelcontextprotocol.io) server that lets an LLM operate Weles
through the app's own HTTP API — the same endpoints the browser uses — instead of
clicking the UI. It can also run the Allegro order sync on a fixed interval
without any LLM involved.

The server lives in `mcp_server/` at the repository root, as a separate package:

- it needs only `mcp` and `httpx`, so the backend's FastAPI/WeasyPrint stack is not
  duplicated in the MCP environment;
- it never imports the backend or touches `data/state.json`, so the app's
  behaviour and deployment stay exactly as they are;
- the Docker image does not ship it — you run it on the machine that talks to the
  app (and to the printer).

Every tool calls a route that already exists. The route is named in the tool
description and in the tables below.

## Requirements

- Python 3.11 or newer
- A running Weles app reachable over HTTP (default `http://127.0.0.1:3001`)
- The app's access token (`PACKING_ACCESS_TOKEN` from the app's `.env`, at least
  32 characters — with a shorter one the app answers 503 and no tool can work)
- For printing: CUPS with a configured printer and the `lp` command

## Install and run

```sh
git clone https://github.com/majorlupa/packing.git
cd packing
python3 -m venv .venv
.venv/bin/pip install -r mcp_server/requirements.txt
```

Start the server with an environment that points at the app:

```sh
export PACKING_API_URL=http://127.0.0.1:3001
export PACKING_ACCESS_TOKEN='<token from .env>'
export PACKING_PRINTER='Office'          # optional, CUPS default queue otherwise
.venv/bin/python -m mcp_server serve     # MCP over stdio (default)
```

Nothing is printed on stdout except the MCP protocol; logs go to stderr.

Other commands:

```sh
.venv/bin/python -m mcp_server serve --transport streamable-http --host 127.0.0.1 --port 8765
.venv/bin/python -m mcp_server sync-once
.venv/bin/python -m mcp_server sync-loop --interval 300
```

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `PACKING_API_URL` | `http://127.0.0.1:3001` | Base URL of the app. The `/api` prefix is added by the client. |
| `PACKING_ACCESS_TOKEN` | — | Bearer token the app expects. Required for every tool except `get_app_health`. Never logged, never returned by a tool. |
| `PACKING_LANGUAGE` | `en` | `Accept-Language` sent with each request (`pl` or `en`). The app answers messages and renders documents in that language. |
| `PACKING_PRINTER` | CUPS default | Printer queue for `print_label` / `print_document` when the tool call does not name one. |
| `PACKING_LABEL_DIR` | `<tmp>/packing-labels` | Where downloaded PDFs are written when a tool call does not name a path. |
| `PACKING_API_TIMEOUT` | `60` | HTTP timeout in seconds (label creation can poll Allegro for a while). |
| `PACKING_MCP_HOST` | `127.0.0.1` | Bind address for streamable-HTTP. |
| `PACKING_MCP_PORT` | `8765` | Port for streamable-HTTP. |
| `PACKING_MCP_TRANSPORT` | `stdio` | Default transport (`stdio` or `streamable-http`). |
| `PACKING_SYNC_INTERVAL` | `300` | Default `sync-loop --interval`. |
| `PACKING_LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |

The token is also compared in constant time by the app; the MCP server only sends
it in the `Authorization: Bearer …` header.

## Connecting an MCP client

### Claude Desktop

`claude_desktop_config.json` (Settings → Developer → Edit Config), then restart
Claude Desktop:

```json
{
  "mcpServers": {
    "packing": {
      "command": "/opt/packing/.venv/bin/python",
      "args": ["-m", "mcp_server", "serve"],
      "env": {
        "PYTHONPATH": "/opt/packing",
        "PACKING_API_URL": "http://127.0.0.1:3001",
        "PACKING_ACCESS_TOKEN": "<token>",
        "PACKING_PRINTER": "Office"
      }
    }
  }
}
```

### Hermes Agent

In `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  packing:
    command: "/opt/packing/.venv/bin/python"
    args: ["-m", "mcp_server", "serve"]
    cwd: "/opt/packing"
    env:
      PACKING_API_URL: "http://127.0.0.1:3001"
      PACKING_ACCESS_TOKEN: "${PACKING_ACCESS_TOKEN}"   # from ~/.hermes/.env
      PACKING_PRINTER: "Office"
    timeout: 300
```

Hermes exposes the tools with a `mcp_packing_` prefix after a restart.

### Any other client

Use the stdio transport with `command` = the venv's `python`, `args` =
`["-m", "mcp_server", "serve"]`, and the environment above. A client that speaks
Streamable HTTP can instead connect to `http://127.0.0.1:8765/mcp` after starting
`serve --transport streamable-http`.

> The HTTP transport has no authentication of its own and anyone who can reach it
> can operate the app with the configured token. Keep it bound to loopback (the
> default) or put it behind an authenticating reverse proxy.

## Tools

### Status and Allegro

| Tool | Route | What it does |
| --- | --- | --- |
| `get_app_health` | `GET /health` (no token) | Is the app running and is the state file healthy. |
| `get_state_status` | `GET /api/orders/status` | State-file problems (quarantined/repaired records) and whether dry-run is on. |
| `sync_orders` | `POST /api/orders/sync` | The **Pobierz zamówienia** button: pull READY_FOR_PROCESSING orders from Allegro. |
| `get_allegro_auth_status` | `GET /api/orders/auth/status` | Whether the app holds an Allegro authorization. |
| `get_allegro_auth_url` | `GET /api/orders/auth/url` | Authorization URL for the operator to open in a browser. |
| `seed_mock_orders` | `POST /api/orders/seed-mock` | Sample orders; dry-run only (409 otherwise). |
| `finish_day` | `POST /api/orders/zakoncz-dzien` | The **Zakończ dzień** button: archive finished orders. |
| `list_archive` | `GET /api/orders/archive` | Archived Allegro ids with timestamps. |

### Queues and orders

| Tool | Route | What it does |
| --- | --- | --- |
| `list_orders` | `GET /api/orders/` | Orders with optional `status`, `courier` and `search` filters; includes queue counts. |
| `get_order` | `GET /api/orders/` | One order by local id (the API has no single-order route). |
| `mark_order_done` | `POST /api/orders/{id}/done` | The ✓ button on the packing card. |
| `undo_order_done` | `POST /api/orders/{id}/undo-done` | Move a finished order back to packing. |
| `revert_order_to_pending` | `POST /api/orders/{id}/revert-pending` | Send an order back to Oczekujące and detach it from its list. |
| `set_parcel_size` | `PATCH /api/orders/{id}/parcel-size` | Locker size A/B/C for an InPost Paczkomat order. |

### Picking lists

| Tool | Route | What it does |
| --- | --- | --- |
| `list_picking_lists` | `GET /api/picking-lists` | All lists with their order ids. |
| `get_picking_list` | `GET /api/picking-lists` + `GET /api/orders/` | One list with its orders and a consolidated product list (what the UI prints). |
| `create_picking_list` | `POST /api/picking-lists` | **Utwórz listę kompletowania** for the given order ids. |
| `rename_picking_list` | `PATCH /api/picking-lists/{id}` | Rename a list. |
| `revert_picking_list` | `POST /api/picking-lists/{id}/revert` | Undo a list; orders return to pending. |
| `start_packing` | `POST /api/picking-lists/{id}/start-packing` | **Rozpocznij pakowanie**: move the list to packing. |

### Labels, documents and printing

| Tool | Route | What it does |
| --- | --- | --- |
| `get_shipment_info` | `GET /api/print/orders/{id}/shipment` | Existing shipment id and tracking number; never buys anything. |
| `create_label` | `POST /api/print/orders/{id}/label` | Create the shipment (at most once per order), optionally overriding dimensions. |
| `download_label` | `GET /api/print/orders/{id}/label` | Save the label PDF; requires an existing shipment. |
| `print_label` | `POST` then `GET /api/print/orders/{id}/label` + `lp` | Create the shipment if needed, download the PDF and print it. |
| `download_document` | `GET /api/print/custom-doc` or `/api/print/orders/{id}/document` or `/combined` | Save the customer document PDF. |
| `print_document` | same as `download_document` + `lp` | Print the customer document. |

`download_document` / `print_document` take `document`:

- `auto` (default) mirrors the packing card: the custom document when one is
  configured (`GET /api/print/custom-doc/info` → `available`), otherwise the sales
  document;
- `custom`, `sales`, `combined` force one source.

`print_label` returns `shipment_created_now`, the CUPS job id, the printer, the
saved PDF path, and the shipment id plus tracking number. A second call for the
same order reuses the existing shipment (`POST /api/print/orders/{id}/label`
answers with the stored id instead of buying another one).

### Settings

| Tool | Route | What it does |
| --- | --- | --- |
| `get_shipment_settings` | `GET /api/print/shipment-settings` | Default package size, page size, sender block. |
| `update_shipment_settings` | `GET` + `POST /api/print/shipment-settings` | Change length/width/height/weight/page size, keeping the sender block. |
| `get_invoice_settings` | `GET /api/print/invoice-settings` | Which fields the sales document shows, footer text. |
| `update_invoice_settings` | `GET` + `POST /api/print/invoice-settings` | Change those switches and the footer. |
| `get_document_settings` | `GET /api/print/document-settings` | Full template list and the active selection. |
| `list_document_templates` | `GET /api/print/document-settings` | Compact template list with the active flag. |
| `select_document_template` | `POST /api/print/document-templates/{id}/select` | Choose the template printed while packing. |
| `get_custom_doc_info` | `GET /api/print/custom-doc/info` | Whether a custom document is available and its source. |
| `upload_custom_doc` | `POST /api/print/custom-doc` | Upload/replace the custom PDF from a local file path. |
| `delete_custom_doc` | `DELETE /api/print/custom-doc` | Delete the uploaded custom PDF. |

## Sidebar coverage

| Sidebar item / action | Tool |
| --- | --- |
| Kolejki: Oczekujące / Kompletowanie / Pakowanie / Gotowe + counters | `list_orders` |
| ↻ Pobierz zamówienia | `sync_orders` |
| Autoryzuj Allegro | `get_allegro_auth_status`, `get_allegro_auth_url` |
| Zakończ dzień | `finish_day` |
| Ustawienia → Dokumenty: invoice switches + footer | `get_invoice_settings`, `update_invoice_settings` |
| Ustawienia → Dokumenty: custom PDF upload/delete | `get_custom_doc_info`, `upload_custom_doc`, `delete_custom_doc` |
| Ustawienia → Dokumenty: template editor, template choice | `get_document_settings`, `list_document_templates`, `select_document_template` |
| Ustawienia → Wysyłka: package dimensions, label page size | `get_shipment_settings`, `update_shipment_settings` |
| Ustawienia → Archiwum | `list_archive` |
| Oczekujące: select products → Utwórz listę kompletowania | `create_picking_list` |
| Oczekujące: Wczytaj zamówienia testowe (dry run only) | `seed_mock_orders` |
| Kompletowanie: rename / revert / start packing | `rename_picking_list`, `revert_picking_list`, `start_packing` |
| Kompletowanie: print picking list | `get_picking_list` (the UI prints it client-side; there is no PDF route, so the tool returns the consolidated items) |
| Pakowanie: parcel size A/B/C | `set_parcel_size` |
| Pakowanie: dimensions and weight for couriers | `create_label` / `print_label` parameters |
| Pakowanie: label button (create + print) | `create_label`, `print_label`, `download_label`, `get_shipment_info` |
| Pakowanie: Dokument / Własny dokument | `download_document`, `print_document` |
| Pakowanie: ↩ revert, ✓ done | `revert_order_to_pending`, `mark_order_done` |
| Gotowe: ↩ undo | `undo_order_done` |
| Language switch | `PACKING_LANGUAGE` sent as `Accept-Language` |

Deliberately not exposed:

- first-run Allegro credentials (`POST /api/setup` needs the browser's exact
  origin and a one-time setup token — an MCP client is not that browser);
- the document *editor* block model (`POST /api/print/document-settings`): it is a
  nested canvas JSON, not something a tool should drive. Use the UI for authoring
  and `select_document_template` to choose an existing one.

## Scheduled Allegro sync (no LLM)

The app has no background scheduler — the browser merely refreshes its view every
60 s (`frontend/static/app.js`), and the sync only happens when someone presses
the button or calls `POST /api/orders/sync`. This package therefore ships two
headless commands that call the same route:

```sh
python -m mcp_server sync-once                  # one sync, exit code 1 on failure
python -m mcp_server sync-loop --interval 300   # sync every 5 minutes until stopped
```

### systemd: long-running loop

`/etc/packing-mcp.env` (mode `600`):

```sh
PACKING_API_URL=http://127.0.0.1:3001
PACKING_ACCESS_TOKEN=<token>
PACKING_PRINTER=Office
PACKING_LABEL_DIR=/var/lib/packing/labels
```

`/etc/systemd/system/packing-sync.service`:

```ini
[Unit]
Description=Weles Allegro order sync (interval loop)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
# The user that may talk to the app and print (member of lp, or the queue's owner).
User=packing
WorkingDirectory=/opt/packing
EnvironmentFile=/etc/packing-mcp.env
ExecStart=/opt/packing/.venv/bin/python -m mcp_server sync-loop --interval 300
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now packing-sync.service
journalctl -u packing-sync -f
```

A failed tick (Allegro down, authorization expired) is logged and retried on the
next interval; the service keeps running.

### systemd timer: one-shot per interval

```ini
# /etc/systemd/system/packing-sync.service
[Unit]
Description=Weles Allegro order sync (one shot)

[Service]
Type=oneshot
User=packing
WorkingDirectory=/opt/packing
EnvironmentFile=/etc/packing-mcp.env
ExecStart=/opt/packing/.venv/bin/python -m mcp_server sync-once
```

```ini
# /etc/systemd/system/packing-sync.timer
[Unit]
Description=Sync Weles orders every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
```

```sh
sudo systemctl enable --now packing-sync.timer
systemctl list-timers packing-sync.timer
```

### cron

```cron
*/5 * * * * cd /opt/packing && set -a && . /etc/packing-mcp.env && set +a && \
  .venv/bin/python -m mcp_server sync-once >> /var/log/packing-sync.log 2>&1
```

Do not run the loop and the timer at the same time; one schedule is enough.

## Printing

Labels and documents are printed by the CUPS client:

```sh
sudo apt-get install cups-client            # provides lp and lpstat
lpstat -p -d                                # list queues and the default one
lp -d Office -o media=A6 some.pdf           # sanity check outside the app
```

- The printer is `PACKING_PRINTER`, or the `printer` tool argument, or the CUPS
  default queue.
- Page size comes from the app's shipping settings (`label_format=PDF`,
  `page_size=A6`/`A4`) and is applied when the label PDF is downloaded from
  Allegro — set it with `update_shipment_settings(page_size="A4")` when your
  printer needs A4.
- The process running the MCP server must be allowed to print (member of `lp`, or
  the queue shared for that user).
- `print_label`/`print_document` save the PDF under `PACKING_LABEL_DIR` before
  calling `lp`, so a failed job can be reprinted with
  `lp -d Office <path>` and the file path is returned in the tool result.
- Without a working `lp` the tools return an actionable error; use
  `download_label` / `download_document` to fetch the PDF only.

## Safety notes

- Creating a shipment is a real carrier booking. The owner's rule is that a label
  only becomes billable when the courier scans it, so `print_label` creates the
  shipment automatically — but the app still creates at most one shipment per
  order and reuses it on later calls.
- `PACKING_SHIPMENT_DRY_RUN=true` on the app side makes shipment creation and
  labels simulated (`dry-run-…` ids, blank PDFs) and enables sample orders. Never
  enable it on a real queue.
- `finish_day` archives every order in the "done" status and removes it from the
  queue; archived Allegro ids are never synced again.
- `delete_custom_doc` deletes the uploaded PDF from the app's data volume. An
  uploaded file is not backed up by the state file.
- Tools report the app's error text (including Allegro failures and 409
  conflicts) instead of a bare status code.

## Tests

```sh
pip install -r mcp_server/requirements.txt -r backend/requirements-dev.txt
python -m pytest -q mcp_server/tests
ruff check mcp_server
```

The tests use `httpx.MockTransport` for every tool, so no app and no network are
needed, and `shutil.which` / `subprocess.run` are patched so `lp` is never
executed.
