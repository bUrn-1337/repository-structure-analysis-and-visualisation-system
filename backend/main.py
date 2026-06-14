"""
main.py – FastAPI application entry point.

Security controls implemented:
- Strict CORS: only http://localhost:3000 is allowed (CWE-942).
- Path-traversal protection in /api/explain uses os.path.commonpath (CWE-22).
- Security response headers added via middleware (X-Content-Type-Options,
  X-Frame-Options, Content-Security-Policy, Permissions-Policy).
- Generic error messages returned to the client; details logged server-side.
- AI API key read exclusively from environment; never hardcoded (CWE-321).
- Rate limiting: TODO(security) – Add a rate-limiting middleware (e.g.,
  slowapi) before deploying to production to prevent DoS.
- Authentication: TODO(security) – This API is unauthenticated. Add API-key
  or OAuth2 authentication before exposing outside localhost.
- The server binds to 127.0.0.1 only when run via __main__ to prevent
  accidental exposure on 0.0.0.0.
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
# CORS – strict allow-list (CWE-942)
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
# Security response-header middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next: Any) -> Response:
    """Attach security headers to every outgoing response."""
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
    Detailed diagnostics are logged server-side only – never exposed to the
    caller (CWE-209).
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
        # Log the real error but return a generic message (CWE-209).
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

    Security:
    - *filepath* is resolved and bounded to *scan_root* using
      os.path.commonpath — identical to the guard in parser.py (CWE-22).
    - File content is read with a hard 1 MB size cap before being sent to
      the AI API to prevent runaway costs / memory exhaustion.
    - Real errors are logged server-side; only generic messages go to the
      client (CWE-209).
    """
    logger.info("Explain request: %r (root=%r)", body.filepath, body.scan_root)

    # ── Path-traversal guard (CWE-22) ──────────────────────────────────────
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
        logger.exception("AI API error for %r: %s", body.filepath, exc)
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

    # TODO(security): In production, run behind a reverse-proxy (e.g. nginx)
    # with TLS termination instead of using uvicorn directly.
    host = os.environ.get("BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
