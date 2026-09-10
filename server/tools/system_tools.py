import json
import os
import shlex
import subprocess

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from tools.system_control import system_control_tools
from tools.windows_apps import find_windows_app
from tools.browser_tools import browser_tools

# -------------------------------------------------
# Load application index
# -------------------------------------------------
current_folder = os.path.dirname(__file__)
index_file = os.path.join(current_folder, "app_index.json")

try:
    with open(index_file, "r", encoding="utf-8") as file:
        app_index = json.load(file)
except FileNotFoundError:
    print(f"WARNING: {index_file} not found. `open_app` will only find Windows built-in apps.")
    app_index = {}


# -------------------------------------------------
# Tool: Open Notepad
# -------------------------------------------------
async def open_notepad(params: FunctionCallParams):
    print("DEBUG: open_notepad triggered")
    try:
        subprocess.Popen(["notepad.exe"])
        await params.result_callback("Notepad opened successfully.")
    except Exception as e:
        print(f"ERROR: {e}")
        await params.result_callback(f"Failed to open Notepad: {str(e)}")


# -------------------------------------------------
# Tool: Open Any Application
# -------------------------------------------------
async def open_app(params: FunctionCallParams):
    print(f"DEBUG: open_app triggered with params: {params.arguments}")

    app_name = params.arguments.get("app_name", "").lower().strip()

    if not app_name:
        await params.result_callback("No application name provided.")
        return

    # 1. Windows Built-in Apps
    windows_app = find_windows_app(app_name)
    if windows_app:
        try:
            if windows_app.startswith("ms-"):
                os.startfile(windows_app)
            else:
                subprocess.Popen(shlex.split(windows_app) if " " in windows_app else [windows_app])
            await params.result_callback("Opened successfully.")
            return
        except Exception as e:
            await params.result_callback(f"Failed to open: {str(e)}")
            return

    # 2. Installed Applications
    if app_name in app_index:
        try:
            app_path = app_index[app_name]
            # shell=True is needed here because .lnk shortcuts require the
            # Windows shell to resolve/execute them.
            subprocess.Popen(app_path, shell=True)
            await params.result_callback("Opened successfully.")
            return
        except Exception as e:
            await params.result_callback(f"Failed to open: {str(e)}")
            return

    # 3. Not Found
    await params.result_callback(
        f"Could not find an application named '{app_name}' on this computer."
    )


# -------------------------------------------------
# Tool schemas - this is what actually lets the LLM call the functions above.
# Attaching `handler=` means pipecat auto-registers it once this ToolsSchema
# is passed into the LLMContext; no separate llm.register_function() call needed.
# -------------------------------------------------
open_notepad_schema = FunctionSchema(
    name="open_notepad",
    description="Open the Windows Notepad application.",
    properties={},
    required=[],
    handler=open_notepad,
)

open_app_schema = FunctionSchema(
    name="open_app",
    description=(
        "Open an application installed on the user's Windows computer by name, "
        "e.g. 'chrome', 'spotify', 'calculator', 'notepad'. Use this ONLY when "
        "the user says 'open <app name>' with no search query and no website "
        "domain attached. Do NOT use this for web searches, even if an app "
        "name like 'Chrome' or 'Google' is mentioned alongside a search topic "
        "(use google_search instead). Do NOT use this for opening a specific "
        "URL or domain like 'github.com' (use open_website instead)."
    ),
    properties={
        "app_name": {
            "type": "string",
            "description": "The name of the application to open.",
        }
    },
    required=["app_name"],
    handler=open_app,
)

system_tools = ToolsSchema(
    standard_tools=[
        open_notepad_schema,
        open_app_schema,
        *system_control_tools.standard_tools,
        *browser_tools.standard_tools,
    ]
)
