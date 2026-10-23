"""Fast source-level regression checks; no API keys or desktop required."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"


class SourceIntegrityTests(unittest.TestCase):
    def test_all_python_files_parse(self):
        files = list(SERVER.rglob("*.py"))
        self.assertGreater(len(files), 0)
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_all_major_tool_registries_are_wired(self):
        registry = (SERVER / "system_tools.py").read_text(encoding="utf-8")
        for name in (
            "browser_tools", "file_tools", "memory_tools", "rag_tools",
            "analyst_tools", "vision_tools", "system_control_tools",
        ):
            with self.subTest(name=name):
                self.assertIn(f"*{name}.standard_tools", registry)

    def test_destructive_actions_require_confirmation(self):
        files = (SERVER / "tools" / "file_tools.py").read_text(encoding="utf-8")
        memory = (SERVER / "tools" / "memory_tools.py").read_text(encoding="utf-8")
        controls = (SERVER / "tools" / "system_control.py").read_text(encoding="utf-8")
        self.assertIn("PENDING_DELETE", files)
        self.assertIn("confirmation != expected", files)
        self.assertIn("PENDING_FORGET", memory)
        self.assertIn('confirmation != f"FORGET {query}"', memory)
        self.assertIn("PENDING_POWER", controls)
        self.assertIn("confirmation != expected", controls)

    def test_roadmap_features_have_tool_implementations(self):
        expected = {
            "server/tools/file_tools.py": ("open_folder", "open_file", "search_files", "delete_path"),
            "server/tools/memory_tools.py": ("remember_fact", "recall_memory", "forget_memory"),
            "server/tools/rag_tools.py": ("ingest_document", "ask_documents", "_cosine"),
            "server/tools/analyst_tools.py": ("analyze_dataset", "clean_missing", "clean_duplicates"),
            "server/tools/vision_tools.py": ("inspect_screen", "click_screen", "PENDING_CLICK"),
            "server/tools/browser_tools.py": ("youtube_search", "google_search", "open_website"),
        }
        for relative, symbols in expected.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            for symbol in symbols:
                with self.subTest(file=relative, symbol=symbol):
                    self.assertIn(symbol, source)

    def test_example_env_does_not_contain_real_secrets(self):
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("GROQ_API_KEY=your_key_here", env)
        self.assertIn("CARTESIA_API_KEY=your_key_here", env)
        self.assertNotIn("sk-", env)


if __name__ == "__main__":
    unittest.main()
