"""Local document retrieval using SQLite-backed TF-IDF-style sparse term scoring.

This provides a dependency-light local RAG baseline. It is lexical retrieval, not
a neural embedding model; the LLM receives retrieved excerpts as tool output.
"""
import math
import json
import hashlib
import os
import re
import sqlite3
from pathlib import Path

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams
from tools.observability import observe_tool

DB_PATH = Path(os.getenv("NOVA_RAG_DB", Path.home() / ".nova_ai" / "documents.sqlite3"))
ALLOWED = {".txt", ".md", ".csv", ".json", ".py", ".log", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
MAX_BYTES = 2_000_000


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS chunks(
        id INTEGER PRIMARY KEY, source TEXT NOT NULL, chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL, embedding TEXT, UNIQUE(source, chunk_index))""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    if "embedding" not in columns:
        conn.execute("ALTER TABLE chunks ADD COLUMN embedding TEXT")
    conn.commit()
    return conn


def _tokens(text):
    return re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())


def _ocr_image(image):
    try:
        import pytesseract
    except ImportError as exc:
        raise ImportError("OCR requires pytesseract and the Tesseract OCR executable. Install both to read scanned pages/images.") from exc
    return pytesseract.image_to_string(image)


def _read_text(path):
    if path.suffix.lower() not in ALLOWED:
        raise ValueError(f"Unsupported type {path.suffix}. Supported: {', '.join(sorted(ALLOWED))}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Document exceeds 2 MB safety limit.")
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        from PIL import Image
        with Image.open(path) as image:
            text = _ocr_image(image)
        if not text.strip():
            raise ValueError("OCR did not find readable text in this image.")
        return text
    if path.suffix.lower() == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise ImportError("PDF ingestion requires PyMuPDF. Install with: pip install PyMuPDF") from exc
        with fitz.open(path) as pdf:
            pages = [page.get_text() for page in pdf]
            text = "\n".join(pages).strip()
            if text:
                return text
            # Scanned PDFs often have no embedded text; OCR rendered pages as a fallback.
            try:
                import pytesseract
                from PIL import Image
            except ImportError as exc:
                raise ImportError("This PDF appears scanned. Install Pillow, pytesseract, and the Tesseract OCR executable for OCR.") from exc
            extracted = []
            for page in pdf:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                extracted.append(_ocr_image(image))
            text = "\n".join(extracted).strip()
            if not text:
                raise ValueError("OCR did not find readable text in the scanned PDF.")
            return text
    return path.read_text(encoding="utf-8", errors="replace")


def _chroma_collection():
    """Return a persistent Chroma collection when the optional backend is selected."""
    import chromadb
    path = Path(os.getenv("NOVA_CHROMA_PATH", Path.home() / ".nova_ai" / "chroma"))
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    return client.get_or_create_collection(
        name="nova_documents",
        metadata={"hnsw:space": "cosine"},
    )


def _embed(texts):
    """Return Gemini embeddings when configured; None means lexical fallback."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.embed_content(
        model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        contents=texts,
    )
    vectors = [list(item.values) for item in (getattr(response, "embeddings", None) or [])]
    return vectors if len(vectors) == len(texts) else None


def _cosine(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


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
        try:
            embeddings = _embed(chunks)
        except Exception:
            embeddings = None
        with _db() as conn:
            conn.execute("DELETE FROM chunks WHERE source = ?", (str(path),))
            conn.executemany(
                "INSERT INTO chunks(source, chunk_index, text, embedding) VALUES (?, ?, ?, ?)",
                [(str(path), i, chunk, json.dumps(embeddings[i]) if embeddings else None)
                 for i, chunk in enumerate(chunks)],
            )
        mode = "Gemini vector embeddings" if embeddings else "local lexical retrieval"
        if embeddings and os.getenv("NOVA_RAG_BACKEND", "sqlite").lower() == "chroma":
            try:
                collection = _chroma_collection()
                collection.delete(where={"source": str(path)})
                ids = [hashlib.sha256(f"{path}:{i}".encode()).hexdigest() for i in range(len(chunks))]
                collection.add(
                    ids=ids,
                    documents=chunks,
                    embeddings=embeddings,
                    metadatas=[{"source": str(path), "chunk_index": i} for i in range(len(chunks))],
                )
                mode += " + ChromaDB"
            except Exception as exc:
                mode += " (ChromaDB unavailable; SQLite fallback: " + str(exc)[:160] + ")"
        await params.result_callback(f"Indexed {len(chunks)} text chunks from {path.name} using {mode}. Ask me a question about it.")
    except Exception as exc:
        await params.result_callback(f"Document ingestion failed: {exc}")


async def remove_document(params: FunctionCallParams):
    """Remove indexed chunks only; never delete the source file."""
    raw_path = (params.arguments.get("path") or "").strip()
    if not raw_path:
        await params.result_callback("Provide the path of the indexed document to remove.")
        return
    path = str(Path(raw_path).expanduser().resolve())
    try:
        with _db() as conn:
            cursor = conn.execute("DELETE FROM chunks WHERE source = ?", (path,))
        if os.getenv("NOVA_RAG_BACKEND", "sqlite").lower() == "chroma":
            try:
                _chroma_collection().delete(where={"source": path})
            except Exception:
                pass
        if cursor.rowcount:
            await params.result_callback(f"Removed {cursor.rowcount} indexed chunk(s) for {path}. The original file was not changed.")
        else:
            await params.result_callback(f"No indexed document found for {path}. The original file was not changed.")
    except sqlite3.Error as exc:
        await params.result_callback(f"Could not remove document from the index: {exc}")


async def ask_documents(params: FunctionCallParams):
    question = (params.arguments.get("question") or "").strip()
    if not question:
        await params.result_callback("Provide a question about your indexed documents.")
        return
    try:
        with _db() as conn:
            rows = conn.execute("SELECT source, chunk_index, text, embedding FROM chunks").fetchall()
        if not rows:
            await params.result_callback("No documents are indexed yet. Use ingest_document with a local .txt, .md, .csv, .json, .py, .log, or .pdf/image file first.")
            return
        query_vector = None
        if os.getenv("GEMINI_API_KEY") and any(row[3] for row in rows):
            try:
                vectors = _embed([question])
                query_vector = vectors[0] if vectors else None
            except Exception:
                query_vector = None
        if query_vector and os.getenv("NOVA_RAG_BACKEND", "sqlite").lower() == "chroma":
            try:
                result = _chroma_collection().query(
                    query_embeddings=[query_vector],
                    n_results=4,
                    include=["documents", "metadatas", "distances"],
                )
                docs = result.get("documents", [[]])[0]
                metas = result.get("metadatas", [[]])[0]
                distances = result.get("distances", [[]])[0]
                scored = []
                for document, metadata, distance in zip(docs, metas, distances):
                    row = (metadata.get("source", "unknown"), int(metadata.get("chunk_index", 0)), document, None)
                    scored.append((1.0 - float(distance), row))
                retrieval_mode = "ChromaDB semantic vector search"
            except Exception:
                scored = []
        else:
            scored = []
        if query_vector and not scored:
            scored = []
            for row in rows:
                try:
                    vector = json.loads(row[3]) if row[3] else None
                except (TypeError, json.JSONDecodeError):
                    vector = None
                score = _cosine(query_vector, vector) if vector else 0.0
                if score > 0:
                    scored.append((score, row))
            scored.sort(key=lambda item: item[0], reverse=True)
            retrieval_mode = "semantic vector similarity"
        else:
            query_terms = set(_tokens(question))
            docs = [_tokens(row[2]) for row in rows]
            document_frequency = {term: sum(term in set(doc) for doc in docs) for term in query_terms}
            scored = []
            for row, tokens in zip(rows, docs):
                counts = {}
                for token in tokens:
                    counts[token] = counts.get(token, 0) + 1
                score = sum(
                    (1 + math.log(counts.get(term, 0))) *
                    math.log(1 + len(rows) / (1 + document_frequency.get(term, 0)))
                    for term in query_terms if counts.get(term, 0)
                )
                if score:
                    scored.append((score, row))
            scored.sort(key=lambda item: item[0], reverse=True)
            retrieval_mode = "lexical relevance"
        if not scored:
            await params.result_callback("No relevant excerpts found. Try different keywords or ingest more documents.")
            return
        excerpts = [f"Source: {row[0]} (chunk {row[1] + 1})\n{row[2]}" for _, row in scored[:4]]
        await params.result_callback(
            f"Retrieved using {retrieval_mode}. Answer using these excerpts and say if they do not contain the answer:\n\n"
            + "\n\n---\n\n".join(excerpts)[:8500]
        )
    except sqlite3.Error as exc:
        await params.result_callback(f"Document retrieval failed: {exc}")


rag_tools = ToolsSchema(standard_tools=[
    FunctionSchema(name="ingest_document", description="Index a local text, Markdown, CSV, JSON, Python, log, PDF, or image file for later question answering.", properties={"path":{"type":"string","description":"Full path to document."}}, required=["path"], handler=observe_tool(ingest_document)),
    FunctionSchema(name="remove_document", description="Remove a document from Nova's local search index without deleting or changing the source file.", properties={"path":{"type":"string","description":"Exact path used when the document was indexed."}}, required=["path"], handler=observe_tool(remove_document)),
    FunctionSchema(name="ask_documents", description="Retrieve relevant excerpts from previously indexed local documents to answer a question. Ground answers in the returned excerpts.", properties={"question":{"type":"string","description":"Question to search indexed documents for."}}, required=["question"], handler=observe_tool(ask_documents)),
])
