"""Persistent, local SQLite memory for user-approved facts and preferences."""
import os
import sqlite3
from pathlib import Path

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from tools.observability import observe_tool

DB_PATH = Path(os.getenv("NOVA_MEMORY_DB", Path.home() / ".nova_ai" / "memory.sqlite3"))
PENDING_FORGET = set()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute("""CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL DEFAULT 'general',
        fact TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(category, fact)
    )""")
    connection.commit()
    return connection


def memory_context(limit: int = 20) -> str:
    """Return a compact memory summary suitable for adding to the system prompt."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT category, fact FROM memories ORDER BY id DESC LIMIT ?", (max(1, min(limit, 50)),)
            ).fetchall()
        if not rows:
            return ""
        return "Saved user memory (use only when relevant):\n" + "\n".join(
            f"- [{category}] {fact}" for category, fact in reversed(rows)
        )
    except sqlite3.Error:
        return ""


async def remember_fact(params: FunctionCallParams):
    category = (params.arguments.get("category") or "general").strip()[:40]
    fact = (params.arguments.get("fact") or "").strip()
    if not fact:
        await params.result_callback("Nothing was saved because the memory was empty.")
        return
    try:
        with _connect() as conn:
            conn.execute("INSERT OR IGNORE INTO memories(category, fact) VALUES (?, ?)", (category, fact[:1000]))
        await params.result_callback(f"Saved memory under '{category}'.")
    except sqlite3.Error as exc:
        await params.result_callback(f"Could not save memory: {exc}")


async def recall_memory(params: FunctionCallParams):
    query = (params.arguments.get("query") or "").strip().lower()
    try:
        with _connect() as conn:
            rows = conn.execute("SELECT category, fact, created_at FROM memories ORDER BY id DESC LIMIT 100").fetchall()
        matches = [row for row in rows if not query or query in row[1].lower() or query in row[0].lower()]
        if not matches:
            await params.result_callback("No matching saved memories.")
            return
        await params.result_callback("\n".join(f"[{c}] {fact} (saved {date})" for c, fact, date in matches[:10]))
    except sqlite3.Error as exc:
        await params.result_callback(f"Could not read memory: {exc}")


async def forget_memory(params: FunctionCallParams):
    query = (params.arguments.get("query") or "").strip()
    confirmation = (params.arguments.get("confirmation") or "").strip()
    if not query:
        await params.result_callback("Provide a specific phrase to find saved memories.")
        return
    if query not in PENDING_FORGET:
        PENDING_FORGET.add(query)
        await params.result_callback(f"Nothing deleted yet. Ask the user to confirm in a separate turn by saying exactly: FORGET {query}")
        return
    if confirmation != f"FORGET {query}":
        await params.result_callback(f"Deletion still pending. The exact confirmation is: FORGET {query}")
        return
    PENDING_FORGET.discard(query)
    try:
        # instr() treats percent/underscore as literal characters, unlike LIKE.
        with _connect() as conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE instr(lower(fact), lower(?)) > 0 OR instr(lower(category), lower(?)) > 0",
                (query, query),
            )
        await params.result_callback(f"Deleted {cursor.rowcount} matching memory item(s).")
    except sqlite3.Error as exc:
        await params.result_callback(f"Could not delete memory: {exc}")


memory_tools = ToolsSchema(standard_tools=[
    FunctionSchema(name="remember_fact", description="Save a user-approved preference or fact to local persistent memory. Ask before saving sensitive information.", properties={"category":{"type":"string","description":"Short category such as preference, project, or routine."},"fact":{"type":"string","description":"Non-sensitive fact or preference to remember."}}, required=["fact"], handler=observe_tool(remember_fact)),
    FunctionSchema(name="recall_memory", description="Recall saved preferences or facts from persistent local memory.", properties={"query":{"type":"string","description":"Optional keyword filter; leave empty to list recent memories."}}, required=[], handler=observe_tool(recall_memory)),
    FunctionSchema(name="forget_memory", description="Delete matching saved memories only after the user confirms the exact phrase FORGET <query>.", properties={"query":{"type":"string","description":"Specific keyword or phrase to remove."},"confirmation":{"type":"string","description":"Must be exactly FORGET followed by the query after explicit user confirmation."}}, required=["query","confirmation"], handler=observe_tool(forget_memory)),
])
