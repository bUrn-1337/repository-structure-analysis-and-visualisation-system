"""
Repository scanner to traverse directories, analyze file dependencies, and retrieve git commit stats.
"""
import os
import re
import logging
import subprocess
from pathlib import Path
from typing import TypedDict
logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
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
_PY_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", re.MULTILINE
)
_C_INCLUDE_STD_RE = re.compile(r'^\s*#include\s*<([^>]+)>', re.MULTILINE)
_C_INCLUDE_LOCAL_RE = re.compile(r'^\s*#include\s*"([^"]+)"', re.MULTILINE)
_JS_ES6_IMPORT_RE = re.compile(
    r"""^import\s+(?:type\s+)?(?:[^'"]*\s+from\s+)?['"]([^'"]+)['"]""", re.MULTILINE
)
_JS_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", re.MULTILINE)
# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------
class NodeData(TypedDict, total=False):
    label: str
    loc: int
    fileType: str
    churn: int
class Node(TypedDict, total=False):
    id: str
    data: NodeData
    type: str
    parentId: str
class Edge(TypedDict):
    id: str
    source: str
    target: str
class ScanResult(TypedDict):
    nodes: list[Node]
    edges: list[Edge]
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_resolve(root: Path, candidate: Path) -> Path | None:
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
        common = os.path.commonpath([root_resolved, resolved])
        if common == str(root_resolved):
            return resolved
    except (ValueError, OSError):
        pass
    return None
def _count_loc(path: Path) -> int:
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
            deps.append(name.split(".")[0])
    return list(set(deps))
def _extract_c_includes(content: str) -> list[str]:
    std = _C_INCLUDE_STD_RE.findall(content)
    local = _C_INCLUDE_LOCAL_RE.findall(content)
    return list(set(std + local))
def _js_candidate_paths(base: Path) -> list[Path]:
    """Generate candidate paths for a JS/TS import without an explicit extension."""
    candidates: list[Path] = []
    for ext in ('.jsx', '.tsx', '.js', '.ts', '.json'):
        candidates.append(Path(str(base) + ext))
    candidates.append(base)
    for ext in ('.jsx', '.tsx', '.js', '.ts'):
        candidates.append(base / f'index{ext}')
    return candidates
def _resolve_js_import(root: Path, source_rel: str, import_path: str) -> str | None:
    """Resolve a relative JS/TS import string to a project-relative path."""
    if not import_path.startswith('.'):
        return None
    root_resolved = root.resolve()
    source_dir = Path(source_rel).parent
    candidate_base = (root_resolved / source_dir / import_path).resolve()
    for p in _js_candidate_paths(candidate_base):
        safe = _safe_resolve(root, p)
        if safe and safe.is_file():
            try:
                return str(safe.relative_to(root_resolved))
            except ValueError:
                pass
    return None
def _extract_js_deps(root: Path, source_rel: str, content: str) -> list[str]:
    raw_modules: list[str] = []
    for m in _JS_ES6_IMPORT_RE.finditer(content):
        raw_modules.append(m.group(1))
    for m in _JS_REQUIRE_RE.finditer(content):
        raw_modules.append(m.group(1))
    resolved: list[str] = []
    for mod in set(raw_modules):
        target = _resolve_js_import(root, source_rel, mod)
        if target:
            resolved.append(target)
    return resolved
def _read_file_safe(path: Path, max_bytes: int = 5 * 1024 * 1024) -> str | None:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return None
        with path.open(encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None
def _get_git_churn(root_path: Path) -> dict[str, int]:
    """Get modifications count per file using git log."""
    churn: dict[str, int] = {}
    try:
        result = subprocess.run(
            ["git", "-c", "safe.directory=*", "log", "--name-only", "--pretty=format:"],
            cwd=str(root_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                normalized = line.replace("\\", "/")
                churn[normalized] = churn.get(normalized, 0) + 1
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
        logger.warning("Could not gather git churn metrics: %s", exc)
    return churn
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def scan_directory(root_path_str: str) -> ScanResult:
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
    file_deps: dict[str, list[str]] = {}
    resolved_file_deps: dict[str, list[str]] = {}  # for JS/TS: already-resolved relative paths
    all_rel_paths: set[str] = set()
    churn_metrics = _get_git_churn(root_resolved)
    for dirpath_str, dirnames, filenames in os.walk(root_resolved, topdown=True):
        dirpath = Path(dirpath_str)
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORED_DIRS and not d.startswith(".")
        ]
        rel_dir = str(dirpath.relative_to(root_resolved))
        if rel_dir != ".":
            parent_dir = str(dirpath.parent.relative_to(root_resolved))
            dir_parent = None if parent_dir == "." else parent_dir
            nodes.append(
                Node(
                    id=rel_dir,
                    data=NodeData(label=dirpath.name, loc=0, fileType="directory", churn=0),
                    type="directoryNode",
                    parentId=dir_parent,
                )
            )
        file_parent = None if rel_dir == "." else rel_dir
        for filename in filenames:
            candidate = dirpath / filename
            safe = _safe_resolve(root_resolved, candidate)
            if safe is None:
                continue
            ext = safe.suffix.lower()
            file_type = EXTENSION_MAP.get(ext)
            if file_type is None:
                continue
            rel = str(safe.relative_to(root_resolved))
            all_rel_paths.add(rel)
            loc = _count_loc(safe)
            file_churn = churn_metrics.get(rel, 0)
            nodes.append(
                Node(
                    id=rel,
                    data=NodeData(
                        label=safe.name,
                        loc=loc,
                        fileType=file_type,
                        churn=file_churn,
                    ),
                    parentId=file_parent,
                )
            )
            content = _read_file_safe(safe)
            if content is None:
                file_deps[rel] = []
                continue
            if file_type == "python":
                file_deps[rel] = _extract_python_imports(content)
            elif file_type in ("c", "cpp", "c_header", "cpp_header"):
                file_deps[rel] = _extract_c_includes(content)
            elif file_type in ("javascript", "typescript"):
                resolved_file_deps[rel] = _extract_js_deps(root_resolved, rel, content)
            else:
                file_deps[rel] = []
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
                dep_basename = os.path.basename(dep)
                targets = filename_index.get(dep_basename, [])
            else:
                candidate_names = [f"{dep}.py", f"{dep}/__init__.py"]
                for cname in candidate_names:
                    for rel in all_rel_paths:
                        if rel == cname or rel.endswith(f"/{cname}"):
                            targets.append(rel)
            for target_rel in targets:
                if target_rel == source_rel:
                    continue
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
    for source_rel, targets in resolved_file_deps.items():
        for target_rel in targets:
            if target_rel == source_rel or target_rel not in all_rel_paths:
                continue
            edge_id = f"{source_rel}-->{target_rel}"
            if edge_id not in seen_edges:
                seen_edges.add(edge_id)
                edges.append(Edge(id=edge_id, source=source_rel, target=target_rel))
    return ScanResult(nodes=nodes, edges=edges)
