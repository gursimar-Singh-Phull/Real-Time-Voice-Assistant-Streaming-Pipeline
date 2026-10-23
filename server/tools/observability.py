"""Structured timing/error instrumentation for asynchronous tool handlers."""
import time
from functools import wraps

from loguru import logger


def observe_tool(handler):
    """Log tool duration and uncaught errors without changing handler behavior."""
    @wraps(handler)
    async def wrapped(params):
        started = time.perf_counter()
        name = handler.__name__
        try:
            result = await handler(params)
            logger.bind(tool=name, duration_ms=round((time.perf_counter() - started) * 1000, 2)).info("tool.completed")
            return result
        except Exception:
            logger.bind(tool=name, duration_ms=round((time.perf_counter() - started) * 1000, 2)).exception("tool.failed")
            raise
    return wrapped
