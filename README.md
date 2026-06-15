# 🕸️ RepoScope: Repository Structure Analysis and Visualisation System

An interactive analysis engine that parses local Git repositories to visually map out folder structures, inter-file dependencies, and code complexity metrics. Built with a React Flow frontend and a FastAPI backend, RepoScope makes it easy to onboard, refactor, and understand large codebases.

---

## 💡 Why RepoScope? (How it Compares)

While many online static analysis or AI tools require uploading codebases to external clouds or require heavy configurations, **RepoScope** runs entirely locally with zero-config.

| Feature / Aspect | Online/SaaS Tools | RepoScope |
| :--- | :--- | :--- |
| **Data Privacy** | Code uploaded to external cloud servers | 100% local parsing and SQLite caching |
| **Dependency Mapping** | Requires complex parser configuration | Automatic out-of-the-box Python and C/C++ parsing |
| **LLM Summarisation Cost** | Paid per API request with no cache mechanism | Local SHA-256 content-hash caching (renames/moves don't duplicate costs) |
| **Git Churn Context** | Static visualisations ignoring history | Integrates Git log metrics to highlight high-frequency refactoring zones |

---

## ✨ Key Features

* **Interactive Dependency Graph:** Automatically parses Python (`import` statements) and C/C++ (`#include` directives) to trace architectural hierarchies.
* **Auto-Layout Canvas:** Utilizes React Flow and Dagre to render a clean, Left-to-Right draggable and zoomable infinite canvas.
* **Visual Git Hotspots:** Inspects repository history using local Git logs, highlighting complex files with high modification churn (10+ commits) with a flame icon.
* **Animated Dependency Pathways:** Hovering over a file dims the rest of the canvas and highlights all direct imports and dependents using animated glowing edges.
* **Content-Addressed AI Summarization:** Click any file node to request a concise, 3-sentence summary of what the code does, powered by Gemini.
* **Double-Layer SQLite Cache:** AI summaries are keyed against the SHA-256 of raw file bytes. If you rename or move a file without changing its contents, RepoScope retrieves the cached explanation instantly, saving LLM tokens.
* **Strict Security Bounding:** Implements path-traversal protection (using resolved path checks) and limits file reads to 1 MB and prompt sizes to 12 KB to prevent runaway token costs or memory exhaustion.

---

## 🏗️ Architecture Stack

* **Frontend:** React, Vite, React Flow (`@xyflow/react`), Axios, Lucide Icons.
* **Backend:** Python, FastAPI, Uvicorn, SQLite.
* **AI Integration:** Google Generative AI SDK (powered by `gemini-2.5-flash` or custom overrides).

---

## 🚀 How to Run

### Method 1: Using Docker Compose (Recommended)

Ensure you have Docker and Docker Compose installed.

1. Create a `.env` file inside the `backend/` directory:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
2. Run the application from the root directory:
   ```bash
   docker compose up -d
   ```
3. Open your browser to `http://localhost:3000`.

> [!NOTE]  
> The Docker container mounts `/home/burn/projects` on the host to `/projects` inside the container. To scan your local projects, prefix the path with `/projects/` (e.g. enter `/projects/repository-structure-analysis-and-visualisation-system` in the search bar).

---

### Method 2: Local Installation (Bare-metal)

#### 1. Backend Setup
Navigate to the backend directory, set up your virtual environment, and install dependencies:
```bash
cd backend
python -m venv .venv

# Activate virtual environment
# On Windows: .venv\Scripts\activate
# On macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the `backend/` directory:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Start the FastAPI server:
```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

#### 2. Frontend Setup
In a new terminal window, navigate to the frontend directory, install dependencies, and start the development server:
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your web browser.

---

## 🛡️ Verification Assumptions & Safeguards

To verify the correct functionality, keep in mind the following internal behaviors:
1. **Git Metrics:** Git modification metrics are calculated by calling the local `git log` command. Verification expects that the target folder being scanned is a valid Git repository with commit history.
2. **Path Resolution:** The backend enforces resolved path verification. Path arguments must be absolute paths within the configured container volume mounts (if using Docker) or accessible local directories (if running bare-metal).
3. **Lazy API Load:** The Gemini API client configuration is loaded lazily. If `GEMINI_API_KEY` is missing, the backend will fail-fast with a `503 Service Unavailable` error when trying to summarize files, rather than silently ignoring it.
4. **Token Cost Mitigation:** Files exceeding 1 MB are blocked from explanation, and code content is truncated to 12 KB before prompting, ensuring predictable token usage.
