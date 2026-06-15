# RepoScope: Repository Structure Analysis and Visualisation System

An interactive analysis engine that parses local Git repositories to visually map folder structures, inter-file dependencies, and code complexity metrics. Built with a React Flow frontend and a FastAPI backend, RepoScope makes it easy to onboard, refactor, and understand large codebases.

---

## Why RepoScope?

| Feature | Online/SaaS Tools | RepoScope |
| :--- | :--- | :--- |
| **Data Privacy** | Code uploaded to external servers | 100% local parsing, SQLite caching |
| **Dependency Mapping** | Requires complex configuration | Auto-detected for Python, C/C++, JS/TS |
| **AI Summarisation Cost** | Paid per request, no cache | SHA-256 content-hash cache — renames don't cost extra |
| **Git Context** | Static diagrams, ignores history | Git churn metrics highlight high-frequency files |

---

## Features

- **Interactive Dependency Graph** — Parses Python (`import`), C/C++ (`#include`), and JavaScript/TypeScript (`import`/`require`) to map architectural relationships as a draggable, zoomable canvas.
- **Auto Dagre Layout** — Left-to-right hierarchical layout via Dagre, with files grouped inside their directory containers.
- **Git Hotspot Detection** — Reads `git log` for each file and badges files with 10+ commits with a flame icon.
- **Hover Highlighting** — Hovering a node dims the rest of the canvas and animates its direct dependency edges.
- **AI File Summaries** — Click any node to get a 3-sentence plain-English explanation of what the file does, powered by Groq (llama-3.1-8b-instant).
- **SQLite Cache** — AI summaries are keyed by SHA-256 of file bytes. Renaming or moving a file without changing content returns the cached result instantly.
- **Path-Traversal Protection** — All file paths are resolved and validated to stay within the scanned root. Files over 1 MB are blocked; prompts are capped at 12 KB.

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| Frontend | React 19, Vite, `@xyflow/react`, Dagre, Axios, Lucide Icons |
| Backend | Python 3.11, FastAPI, Uvicorn |
| AI | Groq API (`llama-3.1-8b-instant`) |
| Cache | SQLite (content-hash keyed) |
| Infrastructure | Docker, Docker Compose |

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/scan?path=<dir>` | Scan a directory — returns nodes and edges for React Flow |
| `POST` | `/api/explain` | Get a 3-sentence AI summary for a file |
| `GET` | `/health` | Liveness probe |

Full interactive docs available at `http://localhost:8000/docs` when running.

---

## Getting Started

### Docker (Recommended)

1. Get a free Groq API key at [console.groq.com](https://console.groq.com)

2. Create `backend/.env`:
   ```env
   GROQ_API_KEY=gsk_your_key_here
   ```

3. Start the stack:
   ```bash
   docker compose up -d
   ```

4. Open `http://localhost:3000`

> **Docker path note:** The container mounts `/home/burn/projects` on the host to `/projects` inside Docker. Enter paths as `/projects/my-repo`, not `/home/burn/projects/my-repo`.

---

### Local (Bare-metal)

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Create backend/.env with your Groq key
uvicorn main:app --host 127.0.0.1 --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

---

## Scanning a Repository

1. Enter an absolute path in the top bar (e.g. `/projects/FERN`)
2. Click **Scan Repository**
3. The graph renders with files as nodes and imports/includes as edges
4. Click any file node to open the File Inspector and load the AI summary
5. Hover over any node to highlight its dependency chain

---

## Supported Languages

| Language | Dependency Detection |
| :--- | :--- |
| Python | `import` / `from … import` |
| C / C++ | `#include "…"` (local) and `#include <…>` (stdlib) |
| JavaScript / JSX | ES6 `import` and `require()` (relative paths) |
| TypeScript / TSX | ES6 `import` and `require()` (relative paths) |
| Others (Go, Rust, Java, etc.) | Scanned and shown as nodes; dependency edges not yet extracted |

---

## Safeguards

1. **Git safe.directory** — The backend passes `-c safe.directory=*` to git so Docker volume mounts (owned by the host user) are read correctly.
2. **Path resolution** — `filepath` in `/api/explain` is checked against `scan_root` using `os.path.commonpath`; anything outside is rejected with HTTP 400.
3. **File size cap** — Files over 1 MB are rejected at the explain endpoint; prompt content is truncated to 12 KB.
4. **AI cache** — Cached summaries are stored in `backend/ai_cache.db`. Delete the file or run `DELETE FROM summaries;` to force a fresh analysis.
5. **Lazy key check** — Groq client is initialised on first request. A missing or placeholder key returns HTTP 503 with an actionable error message.
