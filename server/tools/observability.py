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


async def get_runtime_metrics(params):
    """Summarize observed tool calls from the structured rotating log."""
    import json
    from pathlib import Path

    log_path = Path.home() / ".nova_ai" / "logs" / "nova.log"
    if not log_path.is_file():
        await params.result_callback("No runtime log exists yet. Start Nova and use a tool before requesting metrics.")
        return
    stats = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            payload = json.loads(line)
            record = payload.get("record", {})
            extra = record.get("extra", {})
            name = extra.get("tool")
            if not name:
                continue
            entry = stats.setdefault(name, {"durations": [], "completed": 0, "failed": 0})
            message = record.get("message", "")
            if message == "tool.completed":
                entry["completed"] += 1
                if isinstance(extra.get("duration_ms"), (int, float)):
                    entry["durations"].append(float(extra["duration_ms"]))
            elif message == "tool.failed":
                entry["failed"] += 1
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    if not stats:
        await params.result_callback("No structured tool timing records found. Restart Nova after enabling structured logging.")
        return
    lines = ["Tool runtime summary (milliseconds; historical observations, not a latency guarantee):"]
    for name, data in sorted(stats.items()):
        values = sorted(data["durations"])
        average = sum(values) / len(values) if values else 0.0
        p95 = values[min(len(values) - 1, max(0, int(len(values) * 0.95) - 1))] if values else 0.0
        lines.append(
            f"{name}: completed={data['completed']}, failed={data['failed']}, "
            f"avg={average:.1f} ms, p95={p95:.1f} ms"
        )
    await params.result_callback("\\n".join(lines)[:8500])


from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams


observability_tools = ToolsSchema(standard_tools=[
    FunctionSchema(
        name="get_runtime_metrics",
        description="Summarize logged tool call counts, failures, average duration, and p95 duration from Nova's local structured log.",
        properties={},
        required=[],
        handler=observe_tool(get_runtime_metrics),
    )
])
