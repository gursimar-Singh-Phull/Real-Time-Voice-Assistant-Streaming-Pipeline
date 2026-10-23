"""Safe local file and folder tools for Nova AI.

Destructive deletion requires the caller to pass an exact confirmation token.
All operations are local to the machine running the assistant.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

MAX_SEARCH_RESULTS = 50
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".py", ".log", ".yaml", ".yml", ".html", ".xml"}


def _path(raw: str) -> Path:
    value = (raw or "").strip().strip('"')
    if not value:
        raise ValueError("A path is required.")
    return Path(value).expanduser().resolve()


def _open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


async def open_folder(params: FunctionCallParams):
    try:
        path = _path(params.arguments.get("path", ""))
        if not path.exists() or not path.is_dir():
            await params.result_callback(f"Folder not found: {path}")
            return
        _open_path(path)
        await params.result_callback(f"Opened folder {path}.")
    except Exception as exc:
        await params.result_callback(f"Could not open folder: {exc}")


async def list_files(params: FunctionCallParams):
    try:
        folder = _path(params.arguments.get("path", ""))
        if not folder.is_dir():
            await params.result_callback(f"Folder not found: {folder}")
            return
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        limit = max(1, min(int(params.arguments.get("limit", 30)), 100))
        lines = [f"{'[DIR]' if p.is_dir() else '[FILE]'} {p.name}" for p in entries[:limit]]
        suffix = f"\nShowing {len(lines)} of {len(entries)} entries." if len(entries) > limit else ""
        await params.result_callback("\n".join(lines) + suffix if lines else "Folder is empty.")
    except Exception as exc:
        await params.result_callback(f"Could not list folder: {exc}")


async def search_files(params: FunctionCallParams):
    try:
        root = _path(params.arguments.get("folder", ""))
        query = (params.arguments.get("query") or "").strip().lower()
        if not root.is_dir() or not query:
            await params.result_callback("Provide an existing folder and a non-empty file-name search.")
            return
        found = []
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", ".venv"}]
            for name in files:
                if query in name.lower():
                    found.append(str(Path(current) / name))
                    if len(found) >= MAX_SEARCH_RESULTS:
                        break
            if len(found) >= MAX_SEARCH_RESULTS:
                break
        await params.result_callback("\n".join(found) if found else f"No filenames matching '{query}' found.")
    except Exception as exc:
        await params.result_callback(f"File search failed: {exc}")


async def create_text_file(params: FunctionCallParams):
    try:
        path = _path(params.arguments.get("path", ""))
        text = params.arguments.get("content", "")
        if path.exists():
            await params.result_callback("That file already exists. Choose another path; this tool never overwrites files.")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        await params.result_callback(f"Created text file {path}.")
    except Exception as exc:
        await params.result_callback(f"Could not create file: {exc}")


async def copy_or_move(params: FunctionCallParams):
    try:
        source = _path(params.arguments.get("source", ""))
        destination = _path(params.arguments.get("destination", ""))
        operation = (params.arguments.get("operation") or "copy").lower()
        if operation not in {"copy", "move", "rename"}:
            await params.result_callback("Operation must be copy, move, or rename.")
            return
        if not source.exists():
            await params.result_callback(f"Source does not exist: {source}")
            return
        if destination.exists():
            await params.result_callback("Destination already exists; refusing to overwrite it.")
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        if operation == "copy":
            shutil.copy2(source, destination) if source.is_file() else shutil.copytree(source, destination)
        else:
            shutil.move(str(source), str(destination))
        await params.result_callback(f"{operation.title()} completed: {source} -> {destination}")
    except Exception as exc:
        await params.result_callback(f"File operation failed: {exc}")


async def delete_path(params: FunctionCallParams):
    try:
        path = _path(params.arguments.get("path", ""))
        confirmation = (params.arguments.get("confirmation") or "").strip()
        expected = f"DELETE {path.name}"
        if not path.exists():
            await params.result_callback(f"Path not found: {path}")
            return
        if confirmation != expected:
            await params.result_callback(
                f"Deletion not performed. Ask the user to explicitly confirm by saying: {expected}. "
                "Only call again after that exact confirmation."
            )
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        await params.result_callback(f"Deleted {path}.")
    except Exception as exc:
        await params.result_callback(f"Delete failed: {exc}")


def _schema(name, description, properties, required, handler):
    return FunctionSchema(name=name, description=description, properties=properties, required=required, handler=handler)


file_tools = ToolsSchema(standard_tools=[
    _schema("open_folder", "Open an existing local folder in the system file manager.", {"path":{"type":"string","description":"Absolute or home-relative folder path."}}, ["path"], open_folder),
    _schema("list_files", "List files and subfolders in a local folder.", {"path":{"type":"string","description":"Folder path."},"limit":{"type":"integer","description":"Maximum number of entries, 1-100."}}, ["path"], list_files),
    _schema("search_files", "Search recursively for local files by filename, not file contents.", {"folder":{"type":"string","description":"Folder to search."},"query":{"type":"string","description":"Filename text to find."}}, ["folder","query"], search_files),
    _schema("create_text_file", "Create a UTF-8 text file without overwriting an existing file.", {"path":{"type":"string","description":"New file path."},"content":{"type":"string","description":"Full text to write."}}, ["path","content"], create_text_file),
    _schema("copy_or_move_file", "Copy, move, or rename a local file or folder. Refuses to overwrite existing destinations.", {"source":{"type":"string","description":"Existing source path."},"destination":{"type":"string","description":"New destination path."},"operation":{"type":"string","enum":["copy","move","rename"],"description":"Operation to perform."}}, ["source","destination","operation"], copy_or_move),
    _schema("delete_file_or_folder", "Delete a local file or folder only after the user explicitly confirms the exact token DELETE <filename>. This is destructive.", {"path":{"type":"string","description":"Exact target path."},"confirmation":{"type":"string","description":"Must exactly equal DELETE followed by the target's basename, and only be supplied after explicit user confirmation."}}, ["path","confirmation"], delete_path),
])
