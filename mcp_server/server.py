"""MCP server wiring: turns PackingTools methods into MCP tools."""
import functools
import inspect

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .client import PackingClient, PackingError
from .config import Settings
from .tools import PackingTools

# The tool surface, in the order a packing day uses it. Every name is a method of
# PackingTools; its docstring becomes the MCP tool description.
TOOL_NAMES = (
    # connection and app state
    "get_app_health",
    "get_state_status",
    # Allegro sync and end of day
    "sync_orders",
    "get_allegro_auth_status",
    "get_allegro_auth_url",
    "seed_mock_orders",
    "finish_day",
    "list_archive",
    # queues and orders
    "list_orders",
    "get_order",
    "mark_order_done",
    "undo_order_done",
    "revert_order_to_pending",
    "set_parcel_size",
    # picking lists
    "list_picking_lists",
    "get_picking_list",
    "create_picking_list",
    "rename_picking_list",
    "revert_picking_list",
    "start_packing",
    # shipments, labels and documents
    "get_shipment_info",
    "create_label",
    "download_label",
    "print_label",
    "download_document",
    "print_document",
    # settings
    "get_shipment_settings",
    "update_shipment_settings",
    "get_invoice_settings",
    "update_invoice_settings",
    "get_document_settings",
    "list_document_templates",
    "select_document_template",
    "get_custom_doc_info",
    "upload_custom_doc",
    "delete_custom_doc",
)

INSTRUCTIONS = """\
Operate the Weles (Packing) app for an Allegro seller through its HTTP API.

Typical day:
1. sync_orders — pull new Allegro orders into the pending queue.
2. list_orders(status="pending") — decide what to pick; create_picking_list with
   the order ids you want to collect together.
3. start_packing(picking_list_id) — move the list to the packing queue.
4. For each packing order: choose a locker size with set_parcel_size when the
   order is an InPost Paczkomat one, then print_label (creates the shipment at
   most once per order) and print_document for the customer document.
5. mark_order_done, and finish_day when everything is shipped.

Safety:
- print_label and create_label book a real carrier shipment (in dry-run mode they
  are simulated). A label becomes billable only when the courier scans the parcel,
  but never create shipments for orders you are not going to ship.
- finish_day archives every finished order; it does not delete orders in other
  queues.
- Printing needs the CUPS `lp` command and a configured printer (PACKING_PRINTER
  or the CUPS default queue). Use download_label/download_document to inspect a
  PDF without printing.

Errors are returned with the app's own message, for example an Allegro 502 or a
409 conflict. If a token error appears, the operator must set PACKING_ACCESS_TOKEN
for this MCP server; never ask for it in chat.
"""


def as_mcp_tool(method):
    """Report the app's own error message to the model.

    mcp 2.x only treats ``ToolError`` as an anticipated failure and sends its message
    in the result; any other exception is a crash the model sees as "Error executing
    tool <name>". Domain errors stay ``PackingError``, so translate them here.
    """

    @functools.wraps(method)
    async def tool(*args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except PackingError as exc:
            raise ToolError(str(exc)) from exc

    return tool


def create_server(
    settings: Settings | None = None,
    *,
    client: PackingClient | None = None,
) -> MCPServer:
    """Build the MCP server with every tool registered.

    Transport options (host, port) are not part of the server in mcp 2.x; pass them
    to ``MCPServer.run()`` when serving streamable HTTP.
    """
    settings = settings or Settings.from_env()
    tools = PackingTools(client or PackingClient(settings), settings)
    server = MCPServer("packing", instructions=INSTRUCTIONS)
    for name in TOOL_NAMES:
        method = getattr(tools, name)
        server.add_tool(as_mcp_tool(method), name=name, description=inspect.getdoc(method))
    return server
