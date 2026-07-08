from __future__ import annotations

import asyncio
import contextlib


async def is_tcp_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return whether a TCP connection can be established within timeout."""
    writer: asyncio.StreamWriter | None = None
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        return True
    except (OSError, asyncio.TimeoutError):
        return False
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

