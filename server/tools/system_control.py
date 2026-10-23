"""Windows system controls. Destructive power actions require explicit confirmation."""
import ctypes
import os
import subprocess
import sys

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from tools.observability import observe_tool

PENDING_POWER = set()


def _windows_only():
    if sys.platform != "win32":
        raise OSError("This control is supported only on Windows.")


async def lock_pc(params: FunctionCallParams):
    try:
        _windows_only()
        ctypes.windll.user32.LockWorkStation()
        await params.result_callback("Computer locked.")
    except Exception as exc:
        await params.result_callback(f"Failed to lock computer: {exc}")


async def sleep_pc(params: FunctionCallParams):
    try:
        _windows_only()
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        await params.result_callback("Sleep command sent.")
    except Exception as exc:
        await params.result_callback(f"Failed to sleep computer: {exc}")


async def adjust_volume(params: FunctionCallParams):
    action = (params.arguments.get("action") or "").strip().lower()
    if action not in {"up", "down", "mute"}:
        await params.result_callback("Choose volume action: up, down, or mute.")
        return
    try:
        _windows_only()
        # Windows media keys: volume up 0xAF, down 0xAE, mute 0xAD.
        key = {"up": 0xAF, "down": 0xAE, "mute": 0xAD}[action]
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)
        await params.result_callback({"up": "Volume increased.", "down": "Volume decreased.", "mute": "Mute toggled."}[action])
    except Exception as exc:
        await params.result_callback(f"Could not adjust volume: {exc}")


async def power_action(params: FunctionCallParams):
    action = (params.arguments.get("action") or "").strip().lower()
    confirmation = (params.arguments.get("confirmation") or "").strip()
    expected = {"restart": "RESTART COMPUTER", "shutdown": "SHUT DOWN COMPUTER"}
    if action not in expected:
        await params.result_callback("Choose power action: restart or shutdown.")
        return
    if action not in PENDING_POWER:
        PENDING_POWER.add(action)
        await params.result_callback(
            f"No action taken yet. Ask the user to confirm in a separate turn by saying exactly: {expected[action]}."
        )
        return
    if confirmation != expected[action]:
        await params.result_callback(
            f"No action taken. The exact confirmation phrase is: {expected[action]}."
        )
        return
    PENDING_POWER.discard(action)
    try:
        _windows_only()
        command = ["shutdown.exe", "/r", "/t", "0"] if action == "restart" else ["shutdown.exe", "/s", "/t", "0"]
        subprocess.Popen(command)
        await params.result_callback(f"{action.title()} command sent.")
    except Exception as exc:
        await params.result_callback(f"Could not {action} computer: {exc}")


def _schema(name, description, properties, required, handler):
    return FunctionSchema(name=name, description=description, properties=properties, required=required, handler=observe_tool(handler))


system_control_tools = ToolsSchema(standard_tools=[
    _schema("lock_pc", "Lock the Windows computer.", {}, [], lock_pc),
    _schema("sleep_pc", "Put the Windows computer to sleep.", {}, [], sleep_pc),
    _schema("adjust_system_volume", "Increase or decrease Windows volume, or toggle mute.", {
        "action": {"type": "string", "enum": ["up", "down", "mute"], "description": "Volume action."}
    }, ["action"], adjust_volume),
    _schema("power_action", "Restart or shut down Windows ONLY after the user explicitly confirms the exact confirmation phrase. Never infer confirmation.", {
        "action": {"type": "string", "enum": ["restart", "shutdown"], "description": "Power action."},
        "confirmation": {"type": "string", "description": "Must be exactly RESTART COMPUTER or SHUT DOWN COMPUTER after the user explicitly says that phrase."}
    }, ["action", "confirmation"], power_action),
])
