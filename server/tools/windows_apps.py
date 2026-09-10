import json
import os
from difflib import get_close_matches

# ----------------------------------------------------
# Load windows_apps.json
# ----------------------------------------------------

CURRENT_FOLDER = os.path.dirname(os.path.abspath(__file__))

JSON_FILE = os.path.join(
    CURRENT_FOLDER,
    "windows_apps.json"
)

with open(JSON_FILE, "r", encoding="utf-8") as file:
    WINDOWS_APPS = json.load(file)


# ----------------------------------------------------
# Find Windows App
# ----------------------------------------------------

def find_windows_app(app_name):

    app_name = app_name.lower().strip()

    # Exact Match
    if app_name in WINDOWS_APPS:
        return WINDOWS_APPS[app_name]

    # Fuzzy Match
    match = get_close_matches(
        app_name,
        WINDOWS_APPS.keys(),
        n=1,
        cutoff=0.65
    )

    if match:
        return WINDOWS_APPS[match[0]]

    return None