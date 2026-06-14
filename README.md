\# 🕸️ Repository Structure Analysis and Visualisation System



An interactive, agentic analysis engine that parses local Git repositories to visually map out folder structures, inter-file dependencies, and code complexity metrics. Built with a React Flow frontend and a FastAPI backend, this tool makes it easy to onboard, refactor, and understand large local codebases.



\## ✨ Key Features



\* \*\*Interactive Dependency Graph:\*\* Automatically parses Python (`import`) and C/C++ (`#include`) files to map relationships without running the code.

\* \*\*Auto-Layout Canvas:\*\* Utilizes React Flow and Dagre to render a clean, Left-to-Right draggable and zoomable infinite canvas.

\* \*\*Instant AI Summarization:\*\* Click any file node to generate a concise, 3-sentence plain English summary of what the code does, powered by an LLM (Gemini/OpenAI).

\* \*\*Smart Content Caching:\*\* AI summaries are locally cached in an SQLite database using SHA-256 hashing of the file's contents. You only pay for AI analysis when the actual code changes, even if the file is moved or renamed.

\* \*\*Robust Security:\*\* Built-in safeguards against path traversal ($CWE-22$), strict CORS policies, a 1 MB file read limit, and 12 KB LLM context truncation to prevent runaway token costs.



\---



\## 🏗️ Architecture Stack



\* \*\*Frontend:\*\* React, Vite, React Flow (`@xyflow/react`), Axios, Lucide React (Icons).

\* \*\*Backend:\*\* Python, FastAPI, Uvicorn, SQLite.

\* \*\*AI Integration:\*\* `google-generativeai` / `openai` SDK with asynchronous processing and AbortController request cancellation.



\---



\## 🚀 Getting Started



\### Prerequisites

\* Python 3.8+

\* Node.js v18+

\* An API Key from Google AI Studio (Gemini) or OpenAI.



\### 1. Backend Setup

Navigate to the backend directory, set up your virtual environment, and install the dependencies:



```bash

cd backend

python -m venv .venv



\# On Windows: .venv\\Scripts\\activate

\# On Mac/Linux: source .venv/bin/activate



pip install -r requirements.txt



```



Create a `.env` file in the `backend/` directory and add your AI API key:



```env

\# backend/.env

GEMINI\_API\_KEY=your\_api\_key\_here

\# OR OPENAI\_API\_KEY=your\_api\_key\_here



```



Start the FastAPI server:



```bash

uvicorn main:app --host 127.0.0.1 --port 8000 --reload



```



\### 2. Frontend Setup



Open a new terminal window, navigate to the frontend directory, and start the Vite development server:



```bash

cd frontend

npm install

npm run dev



```



\---



\## 🎮 Usage



1\. Open your browser to `http://localhost:3000`.

2\. In the top navigation bar, enter the \*\*absolute path\*\* of a local repository on your machine (e.g., `/Users/dev/projects/my-app` or `C:\\Projects\\my-app`).

3\. Click \*\*Scan Repository\*\*.

4\. Use your mouse or trackpad to pan and zoom around the generated architecture map.

5\. Click on any file node to open the side panel and generate an AI summary of that specific file's purpose.



\---



\## 🛡️ Security Notes



This application is designed to run locally and safely analyze your machine's files:



\* \*\*Path Enforcement:\*\* The API uses `os.path.commonpath` to ensure that no file operations can escape the explicitly provided scanning directory.

\* \*\*Local Bindings:\*\* The backend explicitly binds to `127.0.0.1` (localhost) rather than `0.0.0.0`, preventing exposure to your local network.



\---

