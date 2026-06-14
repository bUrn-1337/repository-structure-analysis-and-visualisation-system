"""
parser.py – Core directory traversal and code parsing logic.

Security notes:
- All resolved file paths are bounded to the root directory to prevent
  path-traversal attacks (CWE-22).
- No user-supplied data is passed to shell commands.
- TODO(security): Consider adding a configurable max-scan-depth and
  max-file-size limit to prevent DoS via extremely deep or large repos.
- TODO(security): Auth / rate-limiting is handled at the API layer (main.py).
"""

import os
import re
import logging
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Directories that are always excluded from scanning.
IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        ".idea",
        ".vscode",
    }
)

# Supported source-file extensions and their logical type names.
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c_header",
    ".hpp": "cpp_header",
    ".hxx": "cpp_header",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".sh": "shell",
    ".bash": "shell",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
}

# Regex patterns for import extraction.
_PY_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", re.MULTILINE
)
_C_INCLUDE_STD_RE = re.compile(r'^\s*#include\s*<([^>]+)>', re.MULTILINE)
_C_INCLUDE_LOCAL_RE = re.compile(r'^\s*#include\s*"([^"]+)"', re.MULTILINE)


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------


class NodeData(TypedDict):
    label: str
    loc: int
    type: str


class Node(TypedDict):
    id: str
    data: NodeData


class Edge(TypedDict):
    id: str
    source: str
    target: str


class ScanResult(TypedDict):
    nodes: list[Node]
    edges: list[Edge]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_resolve(root: Path, candidate: Path) -> Path | None:
    """
    Return *candidate* only if it is strictly inside *root*.

    Uses os.path.commonpath instead of str.startswith to avoid partial-name
    bypass attacks (e.g. /sandbox-evil matching /sandbox).
    """
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
        # commonpath raises ValueError when mixing absolute/relative paths.
        common = os.path.commonpath([root_resolved, resolved])
        if common == str(root_resolved):
            return resolved
    except (ValueError, OSError):
        pass
    return None


def _count_loc(path: Path) -> int:
    """Count non-empty, non-comment lines in *path* (best-effort)."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return sum(
                1
                for line in fh
                if line.strip() and not line.strip().startswith(("#", "//", "/*", "*"))
            )
    except OSError as exc:
        logger.warning("Could not read %s for LoC counting: %s", path, exc)
        return 0


def _extract_python_imports(content: str) -> list[str]:
    deps: list[str] = []
    for m in _PY_IMPORT_RE.finditer(content):
        name = m.group(1) or m.group(2)
        if name:
            # Only keep the top-level package name.
            deps.append(name.split(".")[0])
    return list(set(deps))


def _extract_c_includes(content: str) -> list[str]:
    std = _C_INCLUDE_STD_RE.findall(content)
    local = _C_INCLUDE_LOCAL_RE.findall(content)
    return list(set(std + local))


def _read_file_safe(path: Path, max_bytes: int = 5 * 1024 * 1024) -> str | None:
    """
    Read at most *max_bytes* from *path*.

    Caps file reading to 5 MB to avoid OOM on huge generated/binary files.
    TODO(security): Make max_bytes configurable via environment variable.
    """
    try:
        size = path.stat().st_size
        if size > max_bytes:
            logger.info("Skipping large file %s (%d bytes)", path, size)
            return None
        with path.open(encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_directory(root_path_str: str) -> ScanResult:
    """
    Recursively scan *root_path_str* and return nodes + edges for React Flow.

    Security:
    - *root_path_str* is validated and resolved before any file access.
    - Every encountered path is bounded to the resolved root (path-traversal
      protection, CWE-22).
    - No shell commands are invoked.

    Raises:
        ValueError: If *root_path_str* is empty, does not exist, or is not a
                    directory.
    """
    if not root_path_str or not root_path_str.strip():
        raise ValueError("Path must not be empty.")

    root = Path(root_path_str.strip())
    root_resolved = root.resolve()

    if not root_resolved.exists():
        raise ValueError(f"Path does not exist: {root_path_str!r}")
    if not root_resolved.is_dir():
        raise ValueError(f"Path is not a directory: {root_path_str!r}")

    nodes: list[Node] = []
    edges: list[Edge] = []

    # Map from raw (relative) path string -> list of extracted dependency strings
    # so we can resolve edges in a second pass.
    file_deps: dict[str, list[str]] = {}
    # Map from relative path string -> set of dep strings for quick lookup
    all_rel_paths: set[str] = set()

    # ---- First pass: collect files, compute LoC, extract raw deps ----------
    for dirpath_str, dirnames, filenames in os.walk(root_resolved, topdown=True):
        dirpath = Path(dirpath_str)

        # Prune ignored directories in-place (affects os.walk recursion).
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORED_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            candidate = dirpath / filename

            # Bound to root – defend against symlink escapes.
            safe = _safe_resolve(root_resolved, candidate)
            if safe is None:
                logger.warning(
                    "Skipping %s – outside root boundary.", candidate
                )
                continue

            ext = safe.suffix.lower()
            file_type = EXTENSION_MAP.get(ext)
            if file_type is None:
                continue  # Skip unsupported file types.

            rel = str(safe.relative_to(root_resolved))
            all_rel_paths.add(rel)

            loc = _count_loc(safe)

            nodes.append(
                Node(
                    id=rel,
                    data=NodeData(label=safe.name, loc=loc, type=file_type),
                )
            )

            # Extract dependencies only for supported languages.
            content = _read_file_safe(safe)
            if content is None:
                file_deps[rel] = []
                continue

            if file_type == "python":
                file_deps[rel] = _extract_python_imports(content)
            elif file_type in ("c", "cpp", "c_header", "cpp_header"):
                file_deps[rel] = _extract_c_includes(content)
            else:
                file_deps[rel] = []

    # ---- Second pass: resolve edges -----------------------------------------
    # Build a lookup: filename (without directory) -> rel paths to handle local
    # #include "header.h" style references.
    filename_index: dict[str, list[str]] = {}
    for rel in all_rel_paths:
        basename = os.path.basename(rel)
        filename_index.setdefault(basename, []).append(rel)

    seen_edges: set[str] = set()

    for source_rel, deps in file_deps.items():
        source_ext = Path(source_rel).suffix.lower()
        source_type = EXTENSION_MAP.get(source_ext, "")

        for dep in deps:
            targets: list[str] = []

            if source_type in ("c", "cpp", "c_header", "cpp_header"):
                # dep is a filename like "utils.h" or a path like "include/utils.h"
                dep_basename = os.path.basename(dep)
                targets = filename_index.get(dep_basename, [])
            else:
                # Python: dep is a top-level package; try to match to a .py file
                # with that name at any nesting level.
                candidate_names = [f"{dep}.py", f"{dep}/__init__.py"]
                for cname in candidate_names:
                    # Search all_rel_paths for suffix match
                    for rel in all_rel_paths:
                        if rel == cname or rel.endswith(f"/{cname}"):
                            targets.append(rel)

            for target_rel in targets:
                if target_rel == source_rel:
                    continue  # Skip self-loops.
                edge_id = f"{source_rel}-->{target_rel}"
                if edge_id not in seen_edges:
                    seen_edges.add(edge_id)
                    edges.append(
                        Edge(
                            id=edge_id,
                            source=source_rel,
                            target=target_rel,
                        )
                    )

    logger.info(
        "Scan complete: %d nodes, %d edges in %s",
        len(nodes),
        len(edges),
        root_resolved,
    )
    return ScanResult(nodes=nodes, edges=edges)
