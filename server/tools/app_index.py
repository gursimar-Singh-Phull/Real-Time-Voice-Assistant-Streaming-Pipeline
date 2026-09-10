import json
import os

# ==========================================================
# WINDOWS BUILT-IN APPS (protocol handlers / known exe names)
# ==========================================================

WINDOWS_APPS = {
    "calculator": "ms-calculator:",
    "calc": "ms-calculator:",

    "camera": "microsoft.windows.camera:",
    "camara": "microsoft.windows.camera:",

    "settings": "ms-settings:",
    "photos": "ms-photos:",
    "clock": "ms-clock:",
    "paint": "mspaint",
    "notepad": "notepad",
}

# ==========================================================
# SETTINGS
# ==========================================================

CURRENT_FOLDER = os.path.dirname(os.path.abspath(__file__))
SERVER_ROOT = os.path.dirname(CURRENT_FOLDER)  # parent of tools/, where bot.py and system_tools.py live

# app_index.json must live next to system_tools.py (server root), since that's
# where it looks for it. windows_apps.json stays here in tools/, since that's
# where windows_apps.py looks for it.
APP_INDEX_FILE = os.path.join(SERVER_ROOT, "app_index.json")
WINDOWS_APPS_FILE = os.path.join(CURRENT_FOLDER, "windows_apps.json")

SEARCH_FOLDERS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    os.environ.get("LOCALAPPDATA"),

    os.path.join(
        os.environ.get("PROGRAMDATA", ""),
        r"Microsoft\Windows\Start Menu\Programs"
    ),

    os.path.join(
        os.environ.get("APPDATA", ""),
        r"Microsoft\Windows\Start Menu\Programs"
    ),
]

IGNORE = {
    "uninstall",
    "setup",
    "installer",
    "update",
    "updater",
    "helper",
    "repair",
    "crash",
    "crashpad",
    "service",
    "broker",
    "daemon",
    "notification",
    "python",
    "pythonw",
    "java",
    "jdk",
    "jre",
    "redis",
    "mysql",
}

# ==========================================================
# INDEX INSTALLED APPLICATIONS
# ==========================================================

app_index = {}

print("=" * 60)
print("INDEXING APPLICATIONS")
print("=" * 60)

for folder in SEARCH_FOLDERS:

    if not folder:
        continue

    if not os.path.exists(folder):
        continue

    print(f"Searching: {folder}")

    for root, dirs, files in os.walk(folder):

        # Skip unnecessary folders
        dirs[:] = [
            d for d in dirs
            if d.lower() not in (
                "cache",
                "logs",
                "temp",
            )
        ]

        for file in files:

            if not (
                file.lower().endswith(".exe")
                or file.lower().endswith(".lnk")
            ):
                continue

            name = os.path.splitext(file)[0].lower()

            if any(word in name for word in IGNORE):
                continue

            path = os.path.join(root, file)

            if name not in app_index:
                app_index[name] = path

print()
print("Creating aliases...")

# ==========================================================
# AUTOMATIC ALIASES
# ==========================================================

aliases = {}

for name, path in app_index.items():

    words = name.split()

    # "google chrome" -> "chrome"
    if len(words) > 1:

        last_word = words[-1]

        if last_word not in app_index:
            aliases[last_word] = path

# ==========================================================
# MANUAL ALIASES
# ==========================================================

manual_aliases = {
    "google chrome": "chrome",
    "chrome browser": "chrome",

    "visual studio code": "code",
    "vs code": "code",

    "mozilla firefox": "firefox",

    "microsoft edge": "msedge",
    "edge": "msedge",

    "discord app": "discord",

    "spotify music": "spotify",

    "notepad++": "notepad++",
}

for alias, real_name in manual_aliases.items():

    if real_name in app_index:
        aliases[alias] = app_index[real_name]

app_index.update(aliases)

# ==========================================================
# SORT + SAVE
# ==========================================================

app_index = dict(sorted(app_index.items()))

with open(APP_INDEX_FILE, "w", encoding="utf-8") as file:
    json.dump(app_index, file, indent=4)

with open(WINDOWS_APPS_FILE, "w", encoding="utf-8") as file:
    json.dump(WINDOWS_APPS, file, indent=4)

print()
print("=" * 60)
print("Finished")
print(f"Applications Indexed : {len(app_index)}")
print(f"Saved To             : {APP_INDEX_FILE}")
print(f"Windows apps saved to: {WINDOWS_APPS_FILE}")
print("=" * 60)