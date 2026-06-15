"""
FastAPI application defining the API endpoints for RepoScope.
"""

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from parser import scan_directory, ScanResult
import ai_service

# Load .env from the directory containing this file (backend/.env)
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Repository Structure Analysis API",
    description=(
        "Scans a local directory and returns a React Flow–compatible graph "
        "representing the repository's architecture."
    ),
    version="0.1.0",
    # Disable automatic /docs and /redoc in production if desired.
    # docs_url=None, redoc_url=None,
)

# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS: list[str] = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],   # POST added for /api/explain.
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Response-header middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next: Any) -> Response:
    """Attach headers to every outgoing response."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none';"
    )
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/scan", response_model=None, summary="Scan a local directory")
async def scan(
    path: str = Query(
        ...,
        description=(
            "Absolute or relative path to the local directory to scan. "
            "The path must be a directory accessible by the server process."
        ),
        min_length=1,
        max_length=4096,
    ),
) -> JSONResponse:
    """
    Scan *path* and return a React Flow graph payload.

    The response contains two lists:
    - **nodes** – one entry per source file found.
    - **edges** – one entry per detected dependency between files.

    Errors surface as HTTP 400 (bad input) or 500 (unexpected server error).
    Detailed diagnostics are logged server-side only.
    """
    logger.info("Received scan request for path: %r", path)
    try:
        result: ScanResult = scan_directory(path)
    except ValueError as exc:
        # Input validation failure – safe to relay a short message.
        logger.warning("Invalid scan path %r: %s", path, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        logger.error("Permission denied scanning %r: %s", path, exc)
        raise HTTPException(
            status_code=403,
            detail="Permission denied: the server cannot read the specified path.",
        ) from exc
    except Exception as exc:  # pylint: disable=broad-except
        # Log the actual error details and return a generic user-friendly message
        logger.exception("Unexpected error while scanning %r: %s", path, exc)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please check the server logs.",
        ) from exc

    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# /api/explain – AI file explanation with SHA-256 cache
# ---------------------------------------------------------------------------

class ExplainRequest(BaseModel):
    """Request body for the /api/explain endpoint."""

    filepath:  str
    scan_root: str

    @field_validator("filepath", "scan_root")
    @classmethod
    def _must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must not be empty.")
        if len(v) > 4096:
            raise ValueError("Field exceeds maximum allowed length.")
        return v.strip()


@app.post("/api/explain", response_model=None, summary="AI explanation for a file")
async def explain(body: ExplainRequest) -> JSONResponse:
    """
    Return a 3-sentence AI-generated summary of the requested file.
    """
    logger.info("Explain request: %r (root=%r)", body.filepath, body.scan_root)

    # ── Path-traversal validation ──────────────────────────────────────
    try:
        root_resolved = Path(body.scan_root).resolve()
        file_resolved = Path(body.filepath).resolve()

        if not root_resolved.is_dir():
            raise HTTPException(status_code=400, detail="scan_root is not a directory.")

        common = os.path.commonpath([root_resolved, file_resolved])
        if common != str(root_resolved):
            logger.warning(
                "Path-traversal attempt blocked: file=%r root=%r",
                body.filepath, body.scan_root,
            )
            raise HTTPException(
                status_code=400,
                detail="Requested file is outside the scan root.",
            )

        if not file_resolved.is_file():
            raise HTTPException(status_code=404, detail="File not found.")

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Path resolution error: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid path.") from exc

    # ── Read file (1 MB hard cap) ───────────────────────────────────────────
    MAX_READ_BYTES = 1 * 1024 * 1024
    try:
        file_size = file_resolved.stat().st_size
        if file_size > MAX_READ_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large to explain ({file_size:,} bytes; max 1 MB).",
            )
        content_bytes = file_resolved.read_bytes()
    except HTTPException:
        raise
    except PermissionError as exc:
        logger.error("Permission denied reading %r: %s", body.filepath, exc)
        raise HTTPException(
            status_code=403,
            detail="Permission denied: cannot read the requested file.",
        ) from exc
    except OSError as exc:
        logger.error("OS error reading %r: %s", body.filepath, exc)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please check the server logs.",
        ) from exc

    # ── SHA-256 hash → cache lookup / AI call ───────────────────────────────
    sha256 = ai_service.compute_sha256(content_bytes)
    cached_hit = ai_service.get_cached_summary(sha256) is not None

    try:
        summary = await ai_service.explain_file(content_bytes, sha256)
    except RuntimeError as exc:
        # API key not configured — surface a helpful (non-sensitive) message.
        logger.error("AI service config error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        exc_str = str(exc)
        logger.exception("AI API error for %r: %s", body.filepath, exc)
        if "401" in exc_str or "invalid_api_key" in exc_str or "authentication" in exc_str.lower():
            raise HTTPException(
                status_code=503,
                detail="Groq API key is invalid. Set a valid GROQ_API_KEY in backend/.env and restart.",
            ) from exc
        if "429" in exc_str or "rate_limit" in exc_str.lower():
            raise HTTPException(
                status_code=429,
                detail="Groq rate limit reached. Wait a moment and try again.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="The AI service returned an error. Please try again.",
        ) from exc
    return JSONResponse(
        content={
            "summary":   summary,
            "sha256":    sha256,
            "cached":    cached_hit,
            "filepath":  str(file_resolved.relative_to(root_resolved)),
        }
    )


@app.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dev entry-point – binds to 127.0.0.1 only (never 0.0.0.0)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
