"""Model Context Protocol server for the Packing (Weles) app.

The package is a *client* of the app's existing HTTP API: it never imports the
FastAPI backend, so the runtime image, the state file and the app behaviour stay
untouched. See docs/mcp-server.md for setup and the full tool list.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
