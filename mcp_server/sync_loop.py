"""Interval Allegro sync that runs without an LLM.

The app has no background scheduler of its own (the browser only refreshes its
view every 60 s), so this module calls the same POST /api/orders/sync endpoint the
"Pobierz zamówienia" button uses, on a fixed interval.
"""
import asyncio
import logging
import signal

from .client import PackingClient, PackingError

logger = logging.getLogger("packing_mcp.sync")


async def sync_once(client: PackingClient) -> dict:
    """Run one Allegro sync and log its summary (never the token)."""
    result = await client.sync_orders()
    logger.info(
        "Allegro sync finished: added=%s updated=%s total=%s",
        result.get("added"),
        result.get("updated"),
        result.get("total"),
    )
    return result


async def run_loop(client: PackingClient, interval: float, *, max_iterations: int | None = None) -> int:
    """Sync every ``interval`` seconds until SIGINT/SIGTERM (or ``max_iterations``).

    A failed tick is logged and retried on the next interval: one Allegro outage
    must not stop the service. Returns a process exit code.
    """
    if interval <= 0:
        raise ValueError("interval must be greater than zero")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows or a non-main thread: the default handler still stops the process.
            pass

    iterations = 0
    failures = 0
    while not stop.is_set():
        try:
            await sync_once(client)
            failures = 0
        except PackingError as exc:
            failures += 1
            logger.warning("Allegro sync failed (%s in a row): %s", failures, exc)
        except Exception:
            failures += 1
            logger.exception("Unexpected failure during the Allegro sync")
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        if stop.is_set():
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue
    return 0
