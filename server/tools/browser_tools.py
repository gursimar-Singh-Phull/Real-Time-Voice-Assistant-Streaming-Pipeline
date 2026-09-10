"""
tools/browser_tools.py

Browser-related tools: google_search and open_website.

google_search now accepts an optional `browser` argument so requests like
"search bad bunny on Chrome" actually launch that specific browser with the
search results, instead of always falling back to the OS default browser.

Follows the same FunctionSchema(handler=...) + ToolsSchema pattern as the
rest of this project (see tools/system_control.py / root system_tools.py).
"""

import json
import os
import shlex
import subprocess
import urllib.parse
import webbrowser

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from tools.windows_apps import find_windows_app

# -------------------------------------------------
# Load application index (same file root system_tools.py uses) so a
# specifically-named browser like "chrome" can be launched directly with
# the search URL as an argument, instead of relying on the OS default.
# -------------------------------------------------
current_folder = os.path.dirname(os.path.dirname(__file__))
index_file = os.path.join(current_folder, "app_index.json")

try:
    with open(index_file, "r", encoding="utf-8") as file:
        app_index = json.load(file)
except FileNotFoundError:
    app_index = {}


def _resolve_browser_path(browser_name: str):
    """Look up a browser's launch path the same way open_app does."""
    browser_name = browser_name.lower().strip()

    windows_app = find_windows_app(browser_name)
    if windows_app and not windows_app.startswith("ms-"):
        return windows_app

    if browser_name in app_index:
        return app_index[browser_name]

    return None


def _launch_url(url: str, browser_name: str = ""):
    """
    Try to open `url` in the specifically named browser. Falls back to the
    OS default browser if no browser was named, or if the named browser
    could not be resolved to a launch path.
    """
    if browser_name:
        browser_path = _resolve_browser_path(browser_name)
        if browser_path:
            args = shlex.split(browser_path) if " " in browser_path else [browser_path]
            subprocess.Popen([*args, url])
            return f"in {browser_name.title()}"

    webbrowser.open(url)
    return ""


# -------------------------------------------------
# Tool: Google Search
# -------------------------------------------------
async def google_search(params: FunctionCallParams):
    print(f"DEBUG: google_search triggered with params: {params.arguments}")

    query = (params.arguments.get("query") or "").strip()
    browser_name = (params.arguments.get("browser") or "").strip()

    if not query:
        await params.result_callback("No search query provided.")
        return

    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_query}"

    try:
        where = _launch_url(url, browser_name)
        suffix = f" {where}" if where else ""
        await params.result_callback(f"Searched for '{query}'{suffix}.")
    except Exception as e:
        print(f"ERROR: {e}")
        await params.result_callback(f"Failed to search: {str(e)}")


# -------------------------------------------------
# Tool: Open Website
# -------------------------------------------------
async def open_website(params: FunctionCallParams):
    print(f"DEBUG: open_website triggered with params: {params.arguments}")

    site = (params.arguments.get("url") or "").strip()
    browser_name = (params.arguments.get("browser") or "").strip()

    if not site:
        await params.result_callback("No URL provided.")
        return

    if not site.startswith(("http://", "https://")):
        site = "https://" + site

    try:
        where = _launch_url(site, browser_name)
        suffix = f" {where}" if where else ""
        await params.result_callback(f"Opened {site}{suffix}.")
    except Exception as e:
        print(f"ERROR: {e}")
        await params.result_callback(f"Failed to open website: {str(e)}")


# -------------------------------------------------
# Tool schemas
# -------------------------------------------------
google_search_schema = FunctionSchema(
    name="google_search",
    description=(
        "Search Google for a query and open the results in a web browser. "
        "TRIGGER PHRASES: 'search for X', 'search Google for X', 'search the "
        "web for X', 'look up X', 'google X', 'find information about X', "
        "'search X on <browser>'. Do NOT use this to open applications (use "
        "open_app) or to open a specific named website with no search topic "
        "(use open_website)."
    ),
    properties={
        "query": {
            "type": "string",
            "description": (
                "The exact search query text, e.g. 'bad bunny' or 'AI news'. "
                "Do not include words like 'search for' or the browser name "
                "in this value, just the topic itself."
            ),
        },
        "browser": {
            "type": "string",
            "description": (
                "Optional. Only set this if the user names a specific "
                "browser to search in, e.g. 'search bad bunny on Chrome' -> "
                "browser='chrome'. Leave empty if no browser is named."
            ),
        },
    },
    required=["query"],
    handler=google_search,
)

open_website_schema = FunctionSchema(
    name="open_website",
    description=(
        "Open a specific, named website or domain directly in a web browser "
        "(e.g. github.com, chatgpt.com, youtube.com). Use this ONLY when the "
        "user names an exact site or domain to open. Do NOT use this for "
        "generic app launches like 'open Chrome' (use open_app), and do NOT "
        "use this for search queries with no specific site named (use "
        "google_search)."
    ),
    properties={
        "url": {
            "type": "string",
            "description": "The domain or URL to open, e.g. 'github.com'.",
        },
        "browser": {
            "type": "string",
            "description": (
                "Optional. Only set this if the user names a specific "
                "browser, e.g. 'open github.com in Chrome' -> browser='chrome'. "
                "Leave empty if no browser is named."
            ),
        },
    },
    required=["url"],
    handler=open_website,
)

browser_tools = ToolsSchema(
    standard_tools=[
        google_search_schema,
        open_website_schema,
    ]
)