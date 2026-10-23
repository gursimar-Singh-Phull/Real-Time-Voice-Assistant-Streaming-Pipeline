"""Persistent lightweight task plans for multi-step tool workflows."""
import os
import sqlite3
from pathlib import Path

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from tools.observability import observe_tool

DB_PATH = Path(os.getenv("NOVA_TASK_DB", Path.home() / ".nova_ai" / "tasks.sqlite3"))
VALID_STATES = {"pending", "in_progress", "completed", "blocked", "cancelled"}


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'in_progress',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS task_steps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        step_index INTEGER NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        notes TEXT NOT NULL DEFAULT '',
        UNIQUE(task_id, step_index)
    )""")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    return conn


async def create_task_plan(params: FunctionCallParams):
    title = (params.arguments.get("title") or "").strip()
    steps = params.arguments.get("steps") or []
    if not title or not isinstance(steps, list) or not steps:
        await params.result_callback("Provide a task title and at least one step.")
        return
    steps = [str(step).strip() for step in steps if str(step).strip()]
    if not steps or len(steps) > 20:
        await params.result_callback("A plan must contain between 1 and 20 non-empty steps.")
        return
    try:
        with _db() as conn:
            cursor = conn.execute("INSERT INTO tasks(title) VALUES (?)", (title[:200],))
            task_id = cursor.lastrowid
            conn.executemany(
                "INSERT INTO task_steps(task_id, step_index, description) VALUES (?, ?, ?)",
                [(task_id, i, step[:500]) for i, step in enumerate(steps, start=1)],
            )
        await params.result_callback(f"Created task plan #{task_id}: {title}. {len(steps)} steps. Execute one step at a time and update its status.")
    except sqlite3.Error as exc:
        await params.result_callback(f"Could not create task plan: {exc}")


async def get_task_plan(params: FunctionCallParams):
    try:
        task_id = int(params.arguments.get("task_id", 0))
        with _db() as conn:
            task = conn.execute("SELECT id, title, status, created_at FROM tasks WHERE id = ?", (task_id,)).fetchone()
            steps = conn.execute(
                "SELECT step_index, description, status, notes FROM task_steps WHERE task_id = ? ORDER BY step_index",
                (task_id,),
            ).fetchall()
        if not task:
            await params.result_callback(f"Task plan #{task_id} was not found.")
            return
        lines = [f"Plan #{task[0]}: {task[1]} [{task[2]}] created {task[3]}"]
        lines.extend(f"{i}. [{status}] {desc}" + (f" — {notes}" if notes else "") for i, desc, status, notes in steps)
        await params.result_callback("\n".join(lines))
    except (ValueError, sqlite3.Error) as exc:
        await params.result_callback(f"Could not read task plan: {exc}")


async def cancel_task_plan(params: FunctionCallParams):
    """Cancel a stored plan and its pending/in-progress steps; does not interrupt an active OS/API call."""
    try:
        task_id = int(params.arguments.get("task_id", 0))
        with _db() as conn:
            task = conn.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                await params.result_callback(f"Task plan #{task_id} was not found.")
                return
            conn.execute("UPDATE tasks SET status = 'cancelled' WHERE id = ?", (task_id,))
            conn.execute(
                "UPDATE task_steps SET status = 'cancelled' WHERE task_id = ? AND status IN ('pending', 'in_progress')",
                (task_id,),
            )
        await params.result_callback(f"Cancelled task plan #{task_id}: {task[0]}. Any currently executing external action is not forcibly interrupted.")
    except (ValueError, sqlite3.Error) as exc:
        await params.result_callback(f"Could not cancel task plan: {exc}")


async def update_task_step(params: FunctionCallParams):
    try:
        task_id = int(params.arguments.get("task_id", 0))
        step_index = int(params.arguments.get("step_index", 0))
        status = (params.arguments.get("status") or "").strip().lower()
        notes = (params.arguments.get("notes") or "").strip()[:1000]
        if status not in VALID_STATES:
            await params.result_callback("Status must be pending, in_progress, completed, or blocked.")
            return
        with _db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM task_steps WHERE task_id = ? AND step_index = ?",
                (task_id, step_index),
            ).fetchone()
            if not exists:
                await params.result_callback(f"Step {step_index} was not found in plan #{task_id}.")
                return
            conn.execute(
                "UPDATE task_steps SET status = ?, notes = ? WHERE task_id = ? AND step_index = ?",
                (status, notes, task_id, step_index),
            )
            states = [row[0] for row in conn.execute("SELECT status FROM task_steps WHERE task_id = ?", (task_id,))]
            if states and all(state == "completed" for state in states):
                conn.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
            elif "cancelled" in states:
                conn.execute("UPDATE tasks SET status = 'cancelled' WHERE id = ?", (task_id,))
            elif "blocked" in states:
                conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = ?", (task_id,))
            else:
                conn.execute("UPDATE tasks SET status = 'in_progress' WHERE id = ?", (task_id,))
        await params.result_callback(f"Updated plan #{task_id}, step {step_index}: {status}.")
    except (ValueError, sqlite3.Error) as exc:
        await params.result_callback(f"Could not update task step: {exc}")


task_tools = ToolsSchema(standard_tools=[
    FunctionSchema(
        name="create_task_plan",
        description="Create a persistent plan for a multi-step user request. Use a short title and ordered, actionable steps; do not include destructive actions without their required confirmation step.",
        properties={
            "title": {"type": "string", "description": "Short task title."},
            "steps": {"type": "array", "items": {"type": "string"}, "description": "Ordered plan steps, between 1 and 20."},
        },
        required=["title", "steps"],
        handler=observe_tool(create_task_plan),
    ),
    FunctionSchema(
        name="get_task_plan",
        description="Read the status and notes for a persistent task plan.",
        properties={"task_id": {"type": "integer", "description": "Plan ID returned by create_task_plan."}},
        required=["task_id"],
        handler=observe_tool(get_task_plan),
    ),
    FunctionSchema(
        name="cancel_task_plan",
        description="Cancel a saved task plan and mark pending steps cancelled. This does not forcibly interrupt an OS command or an API request already in progress.",
        properties={"task_id": {"type": "integer", "description": "Task plan ID."}},
        required=["task_id"],
        handler=observe_tool(cancel_task_plan),
    ),
    FunctionSchema(
        name="update_task_step",
        description="Update one task step after attempting it. Mark failures as blocked with notes instead of claiming success.",
        properties={
            "task_id": {"type": "integer", "description": "Task plan ID."},
            "step_index": {"type": "integer", "description": "One-based step index."},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked"], "description": "Current step status."},
            "notes": {"type": "string", "description": "Optional result or error details."},
        },
        required=["task_id", "step_index", "status"],
        handler=observe_tool(update_task_step),
    ),
])
