# Nova AI — Real-Time Voice Assistant

Nova AI is a Python voice assistant built on Pipecat. It connects speech recognition, an LLM, speech synthesis, and registered tools for browser actions, local Windows control, memory, document retrieval, screen understanding, and data analysis.

> **Platform note:** Local desktop, file, volume, screenshot, and click tools run on the machine hosting the assistant. Run Nova locally on Windows to use those features. A cloud deployment cannot operate your personal Windows desktop.

## Capabilities

| Area | Implemented capability | Notes |
|---|---|---|
| Voice pipeline | Speech-to-text, LLM responses, text-to-speech, interruption support | Requires valid provider credentials and a compatible Pipecat transport |
| Browser | Google search, open a named website, YouTube search | Opens browser result pages; it does not scrape video metadata or promise playback |
| Desktop | Open installed apps and folders; list, search, create, copy, move, and rename files/folders | Refuses to overwrite existing destinations |
| Safety | Confirmed deletion, memory removal, restart, and shutdown | Requires the exact confirmation phrase expected by each tool |
| System | Lock, sleep, volume up/down, mute toggle | System controls are Windows-only |
| Persistent memory | Save, recall, and forget user-approved facts/preferences | Stored locally in SQLite; do not save secrets or sensitive information |
| Document Q&A | Ingest text files, PDFs, and images; retrieve excerpts from indexed documents | Uses Gemini embeddings when configured and falls back to lexical retrieval; scanned-file OCR requires the Tesseract executable. Uses SQLite by default; an optional ChromaDB persistent vector backend is available |
| Vision | Capture and describe the Windows screen; estimate UI element coordinates; confirmed coordinate click | Requires optional Gemini Vision credentials; clicking is gated by a second explicit confirmation |
| Data analyst mode | CSV/Excel summaries, missing values, duplicates, descriptive statistics, top values, correlation, simple natural-language queries, charts, reports, and cleaning | Cleaning writes a new output file and preserves the source |
| Multi-step workflows | Persistent task plans and step tracking | The LLM coordinates tool calls; automatic retry/cancellation and resumable execution are not implemented yet |
| Observability | Rotating logs and tool execution duration/error records | Pipeline metrics are enabled; real end-to-end latency still depends on hardware, transport, and provider response time |

## Architecture

```text
Microphone / transport
        ↓
Speech-to-text (Groq)
        ↓
LLM + registered tool schemas (Groq)
        ↓
Local tools / browser / memory / documents / datasets / optional vision
        ↓
Text-to-speech (Cartesia)
        ↓
Audio response
```

## Requirements

- Python 3.11 or newer
- Windows for desktop, system-control, and screen-interaction features
- Groq API key for the LLM and speech recognition
- Cartesia API key and voice ID for speech synthesis
- Optional Gemini API key for screen understanding and semantic document embeddings; optional ChromaDB package for vector search; Tesseract OCR executable for scanned PDFs/images

## Setup

1. Clone this repository and open a terminal in its root directory.
2. Create and activate a virtual environment.
3. Install the declared dependencies:

   ```bash
   python -m venv .venv
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and fill in your provider credentials:

   ```dotenv
   GROQ_API_KEY=...
   CARTESIA_API_KEY=...
   CARTESIA_VOICE_ID=...
   # Optional:
   GEMINI_API_KEY=...
   GEMINI_VISION_MODEL=gemini-2.5-flash
   GEMINI_EMBEDDING_MODEL=gemini-embedding-001
NOVA_RAG_BACKEND=sqlite  # or chroma
   ```

5. Start the bot from the server directory:

   ```bash
   cd server
   python bot.py
   ```

Use the transport/client configuration supplied by your Pipecat setup. If your project uses Pipecat Cloud, deploy the server separately; local Windows actions will execute on the cloud host, not your PC.

## Example voice requests

- “Search Google for Python decorators.”
- “Find a video about binary trees on YouTube.”
- “Open my Downloads folder.”
- “Find files containing ‘resume’ in their filename under Documents.”
- “Remember that I prefer concise answers.” (Nova should ask before saving a preference.)
- “Index this PDF at C:\\Users\\me\\Documents\\notes.pdf, including OCR for scanned pages if Tesseract is installed.”
- “Ask my indexed documents what they say about database normalization.”
- “Summarize C:\\data\\sales.csv.”
- “Create a chart of the Revenue column in C:\\data\\sales.csv.”
- “What is visible on my screen?”

For deletion, memory removal, restart, shutdown, or screen clicks, follow the tool’s explicit confirmation request. Do not give Nova access to folders you do not want it to read or modify.

## Data and privacy

- Memory and document indexes are stored locally under `~/.nova_ai/` by default.
- Set `NOVA_MEMORY_DB`, `NOVA_RAG_DB`, or `NOVA_TASK_DB` to change the database locations.
- Logs are written to `~/.nova_ai/logs/nova.log`, with rotation and seven-day retention.
- Do not put API keys in source files or commit your real `.env`.
- Indexed documents and saved memories are supplied to the model only as context for relevant requests; avoid ingesting confidential documents unless you accept sending retrieved excerpts to your configured LLM provider.
- Screen analysis sends the captured screenshot to Gemini when enabled. Use it only when comfortable with that data flow.
- OCR requires installing the Tesseract application separately; the Python package alone is not enough.

To enable the optional ChromaDB backend, install `pip install -r requirements-optional.txt` and set `NOVA_RAG_BACKEND=chroma` in `.env`. Without ChromaDB or Gemini credentials, Nova uses its local lexical/SQLite retrieval fallback.

## Testing

Run the source-level regression checks:

```bash
python -m compileall -q server
python -m unittest discover -s tests -v
```

GitHub Actions runs these checks on pushes and pull requests. These tests validate Python syntax, registry wiring, and confirmation guards; they do **not** replace an end-to-end microphone/audio/API test on Windows.

## Known limitations

- YouTube search opens the results page; direct video playback and metadata extraction are not implemented.
- Document retrieval uses a local SQLite index. Gemini semantic embeddings are optional; without a configured key, retrieval falls back to lexical scoring.
- Vision and screen interaction are Windows-only and require Gemini configuration. UI coordinates are approximate and can become stale if the screen changes.
- Natural-language data queries intentionally support a small set of safe operations rather than arbitrary generated Python or SQL.
- Tool chaining and recovery depend on the LLM and Pipecat tool-call loop; complex multi-step tasks should be validated before relying on them.
- Latency varies by network, provider, model, and machine. No benchmark figures are claimed until measured in a real run.

## Roadmap

For multi-step requests, Nova can save a task plan and update step states. It does not yet automatically retry or resume long-running tasks after a process restart.

See [server/roadmap](server/roadmap) for the detailed implementation status. A checkbox means the code path exists; live provider integrations and desktop behavior still require local validation.
