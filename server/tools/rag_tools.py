"""Local document retrieval using SQLite-backed TF-IDF-style sparse term scoring.

This provides a dependency-light local RAG baseline. It is lexical retrieval, not
a neural embedding model; the LLM receives retrieved excerpts as tool output.
"""
import math
import os
import re
import sqlite3
from pathlib import Path

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

DB_PATH = Path(os.getenv("NOVA_RAG_DB", Path.home() / ".nova_ai" / "documents.sqlite3"))
ALLOWED = {".txt", ".md", ".csv", ".json", ".py", ".log"}
MAX_BYTES = 2_000_000


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS chunks(
        id INTEGER PRIMARY KEY, source TEXT NOT NULL, chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL, UNIQUE(source, chunk_index))""")
    conn.commit()
    return conn


def _tokens(text):
    return re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())


def _read_text(path):
    if path.suffix.lower() not in ALLOWED:
        raise ValueError(f"Unsupported type {path.suffix}. Supported: {', '.join(sorted(ALLOWED))}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Document exceeds 2 MB safety limit.")
    return path.read_text(encoding="utf-8", errors="replace")


def _chunks(text, size=900, overlap=120):
    text = text.strip()
    if not text:
        return []
    result, start = [], 0
    while start < len(text):
        result.append(text[start:start + size])
        if start + size >= len(text):
            break
        start += size - overlap
    return result


async def ingest_document(params: FunctionCallParams):
    try:
        path = Path((params.arguments.get("path") or "").strip()).expanduser().resolve()
        if not path.is_file():
            await params.result_callback(f"Document not found: {path}")
            return
        chunks = _chunks(_read_text(path))
        if not chunks:
            await params.result_callback("The document contains no readable text.")
            return
        with _db() as conn:
            conn.execute("DELETE FROM chunks WHERE source = ?", (str(path),))
            conn.executemany("INSERT INTO chunks(source, chunk_index, text) VALUES (?, ?, ?)",
                             [(str(path), i, chunk) for i, chunk in enumerate(chunks)])
        await params.result_callback(f"Indexed {len(chunks)} text chunks from {path.name}. Ask me a question about it.")
    except Exception as exc:
        await params.result_callback(f"Document ingestion failed: {exc}")


async def ask_documents(params: FunctionCallParams):
    question = (params.arguments.get("question") or "").strip()
    if not question:
        await params.result_callback("Provide a question about your indexed documents.")
        return
    query_terms = set(_tokens(question))
    try:
        with _db() as conn:
            rows = conn.execute("SELECT source, chunk_index, text FROM chunks").fetchall()
        if not rows:
            await params.result_callback("No documents are indexed yet. Use ingest_document with a local .txt, .md, .csv, .json, .py, or .log file first.")
            return
        docs = [_tokens(row[2]) for row in rows]
        df = {term: sum(term in set(doc) for doc in docs) for term in query_terms}
        scored = []
        for row, tokens in zip(rows, docs):
            counts = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            score = sum((1 + math.log(counts.get(term, 0))) * (math.log(1 + len(rows) / (1 + df.get(term, 0)))) for term in query_terms if counts.get(term, 0))
            if score:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            await params.result_callback("No relevant excerpts found. Try different keywords or ingest more documents.")
            return
        excerpts = [f"Source: {row[0]} (chunk {row[1] + 1})\n{row[2]}" for _, row in scored[:4]]
        await params.result_callback("Relevant document excerpts (answer using these sources and state if they do not contain the answer):\n\n" + "\n\n---\n\n".join(excerpts)[:8500])
    except sqlite3.Error as exc:
        await params.result_callback(f"Document retrieval failed: {exc}")


rag_tools = ToolsSchema(standard_tools=[
    FunctionSchema(name="ingest_document", description="Index a local text, Markdown, CSV, JSON, Python, or log file for later question answering.", properties={"path":{"type":"string","description":"Full path to document."}}, required=["path"], handler=ingest_document),
    FunctionSchema(name="ask_documents", description="Retrieve relevant excerpts from previously indexed local documents to answer a question. Ground answers in the returned excerpts.", properties={"question":{"type":"string","description":"Question to search indexed documents for."}}, required=["question"], handler=ask_documents),
])
