"""
AI explanation service with an SQLite-backed content-hash cache.
Uses SHA-256 of file bytes to cache explanations across renames or moves.
"""

import hashlib
import logging
import os
import sqlite3
from pathlib import Path

from groq import AsyncGroq

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

MAX_CONTENT_BYTES: int = 12_000

_DEFAULT_MODEL = "llama-3.1-8b-instant"

_CACHE_DB_PATH: Path = Path(__file__).parent / "ai_cache.db"

_SYSTEM_PROMPT = (
    "You are a senior software engineer performing code review. "
    "Explain what the provided code does in exactly 3 concise sentences. "
    "Be technical but accessible. Do not use markdown backticks or bullet points."
)

# ── Cache ─────────────────────────────────────────────────────────────────────


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_CACHE_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
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


_conn: sqlite3.Connection = _get_connection()

# ── Client (lazy) ─────────────────────────────────────────────────────────────

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key or api_key == "your_groq_api_key_here":
            raise RuntimeError(
                "GROQ_API_KEY is not configured. "
                "Get a free key at https://console.groq.com/, set it in backend/.env, "
                "then restart the server."
            )
        _client = AsyncGroq(api_key=api_key)
        logger.info("Groq client initialised (model=%s).", _get_model())
    return _client


def _get_model() -> str:
    return os.environ.get("GROQ_MODEL", "").strip() or _DEFAULT_MODEL


# ── Public API ────────────────────────────────────────────────────────────────


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def get_cached_summary(sha256: str) -> str | None:
    row = _conn.execute(
        "SELECT summary FROM summaries WHERE sha256 = ?", (sha256,)
    ).fetchone()
    return row[0] if row else None


def store_summary(sha256: str, summary: str, model: str) -> None:
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
    cached = get_cached_summary(sha256)
    if cached:
        logger.info("Cache HIT for sha256=%.16s…", sha256)
        return cached

    logger.info("Cache MISS for sha256=%.16s… — calling Groq.", sha256)

    content_str = file_content_bytes[:MAX_CONTENT_BYTES].decode("utf-8", errors="replace")
    if len(file_content_bytes) > MAX_CONTENT_BYTES:
        content_str += "\n\n[… file truncated for brevity …]"

    client = _get_client()
    model_name = _get_model()

    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content_str},
        ],
        max_tokens=256,
        temperature=0.3,
    )

    summary: str = (response.choices[0].message.content or "").strip()
    if not summary:
        summary = "The AI returned an empty response. Please try again."

    store_summary(sha256, summary, model_name)
    return summary
