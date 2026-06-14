"""
ai_service.py – AI explanation service with SQLite-backed content-hash cache.

Design:
- Cache key = SHA-256 of raw file bytes (content-addressed, not path-addressed).
  If a file is renamed or moved but its content is unchanged, the cache still hits.
- Cache is stored in a single SQLite database (ai_cache.db) next to this module.
  SQLite is concurrency-safe for the single-writer pattern we use here.
- The Gemini client is configured lazily; it reads the API key
  from the environment (loaded by python-dotenv in main.py).

Security:
- GEMINI_API_KEY is read exclusively from the environment — never hardcoded.
  If the key is absent, the service raises a clear RuntimeError at call time
  rather than silently failing or using a fallback string (CWE-321).
- File content is sent to the Gemini API over HTTPS (enforced by the SDK).
- File content is capped at MAX_CONTENT_BYTES before being sent to prevent
  excessively large / expensive prompts.
- TODO(security): Consider redacting secrets (e.g. API keys inside source files)
  from the content before sending it to a third-party AI API.
- TODO(security): Add retry / circuit-breaker logic and per-IP rate limiting
  before production exposure so a single client cannot burn the API budget.
"""

import hashlib
import logging
import os
import sqlite3
from pathlib import Path

import google.generativeai as genai

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

# Maximum bytes of file content sent to the AI (avoids giant prompt bills).
MAX_CONTENT_BYTES: int = 12_000  # ~3 000 tokens at ~4 bytes/token

# Model used for explanations. Override via GEMINI_MODEL env var.
_DEFAULT_MODEL = "gemini-2.5-flash"

# Path to the SQLite cache database, stored next to this module.
_CACHE_DB_PATH: Path = Path(__file__).parent / "ai_cache.db"

# System prompt sent with every request.
_SYSTEM_PROMPT = (
    "You are a senior software engineer performing code review. "
    "Explain what the provided code does in exactly 3 concise sentences. "
    "Be technical but accessible. Do not use markdown backticks or bullet points."
)

# ── Cache initialisation ──────────────────────────────────────────────────────


def _get_connection() -> sqlite3.Connection:
    """Open (or create) the SQLite cache database and ensure the schema exists."""
    conn = sqlite3.connect(str(_CACHE_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")  # Allow concurrent reads.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS summaries (
            sha256      TEXT PRIMARY KEY,
            summary     TEXT NOT NULL,
            model       TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    return conn


# Module-level connection (safe for single-process use; uvicorn is single-process
# in dev mode).
_conn: sqlite3.Connection = _get_connection()

# ── Gemini client configuration (lazy-initialised) ───────────────────────────

_configured: bool = False


def _configure_client() -> None:
    """
    Ensure the module-level genai client is configured.

    Raises RuntimeError if GEMINI_API_KEY is not set — we deliberately do NOT
    fall back to a hardcoded or default value (CWE-321).
    """
    global _configured
    if not _configured:
        api_key = (
            os.environ.get("GEMINI_API_KEY", "").strip() or
            os.environ.get("GOOGLE_API_KEY", "").strip() or
            os.environ.get("OPENAI_API_KEY", "").strip()  # fallback for ease of transition
        )
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Add it to your backend/.env file and restart the server."
            )
        genai.configure(api_key=api_key)
        _configured = True
        logger.info("Gemini API client configured (model=%s).", _get_model())


def _get_model() -> str:
    return (
        os.environ.get("GEMINI_MODEL", "").strip() or
        os.environ.get("GOOGLE_MODEL", "").strip() or
        _DEFAULT_MODEL
    )


# ── Public API ────────────────────────────────────────────────────────────────


def compute_sha256(content: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of *content*."""
    return hashlib.sha256(content).hexdigest()


def get_cached_summary(sha256: str) -> str | None:
    """Return the cached summary for *sha256*, or None if not present."""
    row = _conn.execute(
        "SELECT summary FROM summaries WHERE sha256 = ?", (sha256,)
    ).fetchone()
    return row[0] if row else None


def store_summary(sha256: str, summary: str, model: str) -> None:
    """Persist *summary* in the cache keyed by *sha256*."""
    _conn.execute(
        """
        INSERT INTO summaries (sha256, summary, model)
        VALUES (?, ?, ?)
        ON CONFLICT(sha256) DO UPDATE SET
            summary    = excluded.summary,
            model      = excluded.model,
            created_at = datetime('now')
        """,
        (sha256, summary, model),
    )
    _conn.commit()
    logger.debug("Cached summary for sha256=%.16s…", sha256)


async def explain_file(file_content_bytes: bytes, sha256: str) -> str:
    """
    Return an AI-generated 3-sentence explanation of *file_content_bytes*.

    1. Check the content-hash cache — return immediately on hit.
    2. On miss, truncate content to MAX_CONTENT_BYTES, call the Gemini API,
       store the result, and return it.

    Args:
        file_content_bytes: Raw bytes of the source file.
        sha256: Pre-computed SHA-256 hex digest of *file_content_bytes*.

    Returns:
        Plain-text explanation string (never HTML/markdown with backticks,
        per the system prompt).

    Raises:
        RuntimeError: If GEMINI_API_KEY is not configured.
        Exception: On API-level failures (propagated to the caller).
    """
    # ── Cache hit ──
    cached = get_cached_summary(sha256)
    if cached:
        logger.info("Cache HIT for sha256=%.16s…", sha256)
        return cached

    logger.info("Cache MISS for sha256=%.16s… — calling Gemini.", sha256)

    # ── Truncate to prevent oversized prompts ──
    content_str = file_content_bytes[:MAX_CONTENT_BYTES].decode(
        "utf-8", errors="replace"
    )
    if len(file_content_bytes) > MAX_CONTENT_BYTES:
        content_str += "\n\n[… file truncated for brevity …]"

    _configure_client()
    model_name = _get_model()

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=_SYSTEM_PROMPT,
    )

    response = await model.generate_content_async(
        content_str,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=256,
            temperature=0.3,
        )
    )

    summary: str = (response.text or "").strip()
    if not summary:
        summary = "The AI returned an empty response. Please try again."

    store_summary(sha256, summary, model_name)
    return summary
