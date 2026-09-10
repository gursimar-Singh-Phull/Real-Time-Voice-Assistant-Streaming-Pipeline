"""
tools_registry.py

Merges system_tools + browser_tools into a single ToolsSchema, and registers
all handlers on the LLM service with debug logging so you can verify in your
console exactly which tool the model picked for every user utterance.

USAGE (in your main.py / bot.py, wherever you currently build `llm` and set
up function calling):

    from tools_registry import build_tools_schema, register_all_tools

    tools = build_tools_schema()
    register_all_tools(llm)
"""

from loguru import logger
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from system_tools import system_tools_schemas, system_tools_handlers
from browser_tools import browser_tools_schemas, browser_tools_handlers


def build_tools_schema() -> ToolsSchema:
    """Combine all tool FunctionSchemas into one ToolsSchema."""
    all_schemas = system_tools_schemas + browser_tools_schemas
    logger.info(
        f"[TOOLS] Registered schemas: {[s.name for s in all_schemas]}"
    )
    return ToolsSchema(standard_tools=all_schemas)


def register_all_tools(llm) -> None:
    """
    Register every tool handler on the given LLM service, wrapped with a
    debug log so every dispatch is visible regardless of which handler
    actually runs. Call this once, after `llm` is constructed.
    """
    all_handlers = {**system_tools_handlers, **browser_tools_handlers}

    for name, handler in all_handlers.items():
        wrapped = _with_dispatch_logging(name, handler)
        llm.register_function(name, wrapped)
        logger.info(f"[TOOLS] Handler registered: {name}")


def _with_dispatch_logging(name, handler):
    async def wrapped(params):
        logger.warning(
            f"[DISPATCH] LLM chose tool='{name}' args={dict(params.arguments)}"
        )
        await handler(params)

    return wrapped