
python
"""
parser.py – Traverse directory trees, parse dependencies, and query Git churn.
Security controls:
- Path-traversal protection strictly enforced via resolve() + os.path.commonpath.
- Subprocess calls use fixed arguments, avoiding shell validation vulnerabilities (CWE-78).
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
            ["git", "log", "--name-only", "--pretty=format:"],
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
    return ScanResult(nodes=nodes, edges=edges)
2. frontend/src/utils/layout.js (Modify)
javascript
/**
 * layout.js – Automatic graph layout using Dagre with compound directory nodes.
 */
import dagre from '@dagrejs/dagre';
const NODE_WIDTH  = 200;
const NODE_HEIGHT =  60;
export function applyDagreLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph({ compound: true });
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', ranksep: 110, nodesep: 60 });
  nodes.forEach((n) => {
    const isDir = n.type === 'directoryNode';
    g.setNode(n.id, {
      width: isDir ? 100 : NODE_WIDTH,
      height: isDir ? 100 : NODE_HEIGHT,
    });
  });
  nodes.forEach((n) => {
    if (n.parentId) {
      g.setParent(n.id, n.parentId);
    }
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  const laidOutNodes = nodes.map((n) => {
    const pos = g.node(n.id);
    const isDir = n.type === 'directoryNode';
    const width = isDir ? pos.width : NODE_WIDTH;
    const height = isDir ? pos.height : NODE_HEIGHT;
    let position = {
      x: pos.x - width / 2,
      y: pos.y - height / 2,
    };
    if (n.parentId) {
      const parentPos = g.node(n.parentId);
      const parentX = parentPos.x - parentPos.width / 2;
      const parentY = parentPos.y - parentPos.height / 2;
      position = {
        x: position.x - parentX,
        y: position.y - parentY,
      };
    }
    const nodeData = {
      ...n,
      position,
    };
    if (isDir) {
      nodeData.style = {
        width,
        height,
      };
    }
    return nodeData;
  });
  return { nodes: laidOutNodes, edges };
}
3. frontend/src/App.jsx (Modify)
jsx
/**
 * App.jsx – Root application component.
 *
 * Layout: full-screen canvas (React Flow) + floating ControlBar +
 *         collapsible SidePanel on the right.
 *
 * Security: Wires sanitised event handlers; no unsafe HTML injection.
 */
import { useCallback, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  Panel,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useRepositoryScan } from './hooks/useRepositoryScan';
import { useAiSummary }      from './hooks/useAiSummary';
import ControlBar from './components/ControlBar';
import SidePanel  from './components/SidePanel';
import FileNode   from './components/FileNode';
import DirectoryNode from './components/DirectoryNode';
import './App.css';
/** Register custom node types */
const NODE_TYPES = { 
  fileNode: FileNode,
  directoryNode: DirectoryNode,
};
export default function App() {
  const { nodes: fetchedNodes, edges: fetchedEdges, loading, error, scan, scanRoot } =
    useRepositoryScan();
  const {
    summary:      aiSummary,
    loading:      aiLoading,
    error:        aiError,
    fetchSummary: fetchAiSummary,
    reset:        resetAiSummary,
  } = useAiSummary();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [hoveredNode, setHoveredNode] = useState(null);
  // Keep React Flow state in sync with fresh scan results
  const [prevFetched, setPrevFetched] = useState(null);
  if (fetchedNodes !== prevFetched) {
    setPrevFetched(fetchedNodes);
    setNodes(fetchedNodes);
    setEdges(fetchedEdges);
  }
  // Side panel
  const [panelOpen,  setPanelOpen]  = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const onNodeClick = useCallback((_event, node) => {
    // Ignore folder node clicks in the SidePanel inspector
    if (node.type === 'directoryNode') return;
    const fileRelPath = node.data.path || node.id;
    const absFilePath = scanRoot
      ? `${scanRoot}/${fileRelPath}`.replace(/\/+/g, '/')
      : fileRelPath;
    setSelectedFile({
      path:     fileRelPath,
      absPath:  absFilePath,
      label:    node.data.label,
      loc:      node.data.loc,
      fileType: node.data.fileType,
      churn:    node.data.churn,
    });
    setPanelOpen(true);
    resetAiSummary();
    if (scanRoot) {
      fetchAiSummary(absFilePath, scanRoot);
    }
  }, [scanRoot, fetchAiSummary, resetAiSummary]);
  const closePanel = useCallback(() => {
    setPanelOpen(false);
  }, []);
  // Hover highlighting node/edge calculations
  const onNodeMouseEnter = useCallback((_event, node) => {
    if (node.type === 'directoryNode') return;
    setHoveredNode(node.id);
  }, []);
  const onNodeMouseLeave = useCallback(() => {
    setHoveredNode(null);
  }, []);
  const getHighlightSets = useCallback(() => {
    if (!hoveredNode) return { highlightNodes: null, highlightEdges: null };
    const hlNodes = new Set([hoveredNode]);
    const hlEdges = new Set();
    edges.forEach((edge) => {
      if (edge.source === hoveredNode) {
        hlEdges.add(edge.id);
        hlNodes.add(edge.target);
      } else if (edge.target === hoveredNode) {
        hlEdges.add(edge.id);
        hlNodes.add(edge.source);
      }
    });
    return { highlightNodes: hlNodes, highlightEdges: hlEdges };
  }, [hoveredNode, edges]);
  const { highlightNodes, highlightEdges } = getHighlightSets();
  // Apply styling classes to nodes based on hover state
  const styledNodes = nodes.map((node) => {
    if (!hoveredNode) return node;
    const isHl = highlightNodes.has(node.id);
    const isDir = node.type === 'directoryNode';
    // We do not dim parent directory containers if they contain highlighted children
    return {
      ...node,
      className: `${node.className || ''} ${
        isHl ? 'node-highlighted' : isDir ? 'node-group-transparent' : 'node-dimmed'
      }`.trim(),
    };
  });
  // Apply styling classes to edges based on hover state
  const styledEdges = edges.map((edge) => {
    if (!hoveredNode) return edge;
    const isHl = highlightEdges.has(edge.id);
    return {
      ...edge,
      animated: isHl,
      className: `${edge.className || ''} ${
        isHl ? 'edge-highlighted' : 'edge-dimmed'
      }`.trim(),
    };
  });
  const isEmpty = nodes.length === 0 && !loading;
  return (
    <div className="app-shell">
      {/* Canvas */}
      <div className="canvas-area">
        <ReactFlow
          nodes={styledNodes}
          edges={styledEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onNodeMouseEnter={onNodeMouseEnter}
          onNodeMouseLeave={onNodeMouseLeave}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.18, maxZoom: 1.4 }}
          minZoom={0.08}
          maxZoom={3}
          className="rf-canvas"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={28}
            size={1.2}
            color="#1e1e38"
          />
          <Controls
            showFitView
            showZoom
            showInteractive
            className="rf-controls"
          />
          <MiniMap
            nodeColor={(n) => {
              if (n.type === 'directoryNode') return 'rgba(124, 58, 237, 0.08)';
              const palette = {
                python:     '#7c3aed',
                javascript: '#facc15',
                typescript: '#38bdf8',
                c:          '#fb923c',
                cpp:        '#f97316',
                go:         '#22d3ee',
                rust:       '#fb7185',
              };
              return palette[n.data?.fileType] ?? '#333350';
            }}
            maskColor="rgba(7,7,15,0.72)"
            className="rf-minimap"
          />
          {nodes.length > 0 && (
            <Panel position="bottom-left" className="stats-panel">
              <span className="stats-pill">
                {nodes.filter(n => n.type !== 'directoryNode').length} files &nbsp;·&nbsp; {edges.length} dependencies
              </span>
            </Panel>
          )}
        </ReactFlow>
        {isEmpty && (
          <div className="canvas-empty" aria-label="No scan loaded">
            <div className="canvas-empty__orb" />
            <svg className="canvas-empty__icon" viewBox="0 0 80 80" fill="none" aria-hidden="true">
              <circle cx="40" cy="40" r="38" stroke="#1e1e38" strokeWidth="2" />
              <path d="M24 32h32M24 40h20M24 48h26" stroke="#2a2a50" strokeWidth="2.5" strokeLinecap="round" />
              <circle cx="56" cy="54" r="10" fill="#13131f" stroke="#7c3aed" strokeWidth="1.5" />
              <path d="M53 54h6M56 51v6" stroke="#a855f7" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <p className="canvas-empty__title">Scan a repository to begin</p>
            <p className="canvas-empty__sub">
              Enter an absolute directory path above and click <strong>Scan Repository</strong>.
            </p>
          </div>
        )}
        <ControlBar onScan={scan} loading={loading} error={error} />
      </div>
      <SidePanel
        isOpen={panelOpen}
        onClose={closePanel}
        fileData={selectedFile}
        aiSummary={aiSummary}
        aiLoading={aiLoading}
        aiError={aiError}
        onRetry={() =>
          selectedFile?.absPath && scanRoot
            ? fetchAiSummary(selectedFile.absPath, scanRoot)
            : undefined
        }
      />
    </div>
  );
}
4. frontend/src/App.css (Modify)
Add the following to the end of frontend/src/App.css:

css
/* ── Hover Highlighting Rules ── */
.node-highlighted {
  opacity: 1 !important;
  transform: scale(1.02);
  z-index: 1000 !important;
}
.node-dimmed {
  opacity: 0.22 !important;
  filter: grayscale(40%) blur(0.3px);
  pointer-events: none;
}
.node-group-transparent {
  opacity: 0.95 !important;
}
.edge-highlighted path.react-flow__edge-path {
  stroke: #a855f7 !important;
  stroke-width: 3px !important;
  stroke-dasharray: 5;
  animation: dash 1s linear infinite;
  opacity: 1 !important;
}
.edge-dimmed {
  opacity: 0.08 !important;
}
@keyframes dash {
  from {
    stroke-dashoffset: 10;
  }
  to {
    stroke-dashoffset: 0;
  }
}
5. frontend/src/components/FileNode.jsx (Modify)
jsx
/**
 * FileNode.jsx – Custom React Flow node for source files displaying Hotspot badges.
 */
import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Flame } from 'lucide-react';
import './FileNode.css';
const TYPE_COLOUR = {
  python:      '#a78bfa',
  c:           '#fb923c',
  cpp:         '#f97316',
  c_header:    '#fdba74',
  cpp_header:  '#fcd34d',
  javascript:  '#facc15',
  typescript:  '#38bdf8',
  java:        '#4ade80',
  go:          '#22d3ee',
  rust:        '#fb7185',
  ruby:        '#f43f5e',
  php:         '#818cf8',
  csharp:      '#a3e635',
  kotlin:      '#34d399',
  swift:       '#f87171',
  shell:       '#86efac',
  markdown:    '#94a3b8',
  json:        '#fda4af',
  yaml:        '#c4b5fd',
  toml:        '#fde68a',
  xml:         '#7dd3fc',
  html:        '#f97316',
  css:         '#60a5fa',
};
const FileNode = memo(({ data, selected }) => {
  const colour = TYPE_COLOUR[data.fileType] ?? '#9090b0';
  const isHotspot = data.churn >= 10;
  return (
    <div className={`file-node ${selected ? 'file-node--selected' : ''} ${isHotspot ? 'file-node--hotspot' : ''}`}>
      <Handle type="target" position={Position.Left}  className="file-node__handle" />
      <Handle type="source" position={Position.Right} className="file-node__handle" />
      {/* Accent stripe */}
      <span className="file-node__stripe" style={{ background: colour }} />
      <div className="file-node__body">
        <div className="file-node__title-row">
          <span className="file-node__label truncate" title={data.label}>
            {data.label}
          </span>
          {isHotspot && (
            <span className="file-node__hotspot-badge" title={`High modification churn: ${data.churn} commits`}>
              <Flame size={10} fill="#f97316" />
              <span>Hot</span>
            </span>
          )}
        </div>
        <div className="file-node__meta">
          <span className="file-node__badge" style={{ color: colour, borderColor: colour + '55' }}>
            {data.fileType}
          </span>
          <span className="file-node__loc">{data.loc} LoC</span>
        </div>
      </div>
    </div>
  );
});
FileNode.displayName = 'FileNode';
export default FileNode;
6. frontend/src/components/FileNode.css (Modify)
css
/* FileNode.css */
.file-node {
  position: relative;
  display: flex;
  align-items: stretch;
  width: 200px;
  min-height: 60px;
  background: #13131f;
  border: 1px solid rgba(124, 58, 237, 0.18);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease;
  box-shadow: 0 2px 12px rgba(0,0,0,0.4);
}
.file-node:hover {
  border-color: rgba(168, 85, 247, 0.55);
  box-shadow: 0 0 0 2px rgba(124, 58, 237, 0.18), 0 4px 20px rgba(0,0,0,0.5);
  transform: translateY(-1px);
}
.file-node--selected {
  border-color: #a855f7 !important;
  box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.4), 0 4px 24px rgba(124, 58, 237, 0.3) !important;
}
/* Dynamic glowing border for Git Hotspots */
.file-node--hotspot {
  border-color: rgba(249, 115, 22, 0.35);
  box-shadow: 0 0 10px rgba(249, 115, 22, 0.12);
}
.file-node--hotspot:hover {
  border-color: rgba(249, 115, 22, 0.7);
  box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.18), 0 4px 20px rgba(0,0,0,0.5);
}
/* Accent stripe */
.file-node__stripe {
  width: 4px;
  flex-shrink: 0;
  border-radius: 10px 0 0 10px;
  opacity: 0.85;
}
.file-node__body {
  flex: 1;
  padding: 9px 11px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.file-node__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  min-width: 0;
}
.file-node__label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 500;
  color: #e8e8f4;
  letter-spacing: 0.01em;
}
/* Hotspot warning badge */
.file-node__hotspot-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: rgba(249, 115, 22, 0.15);
  border: 1px solid rgba(249, 115, 22, 0.4);
  border-radius: 4px;
  padding: 1px 4px;
  font-size: 8px;
  font-weight: 700;
  color: #fdba74;
  text-transform: uppercase;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}
.file-node__meta {
  display: flex;
  align-items: center;
  gap: 7px;
}
.file-node__badge {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  padding: 1px 6px;
  border: 1px solid;
  border-radius: 99px;
  opacity: 0.9;
}
.file-node__loc {
  font-size: 9.5px;
  color: #555575;
  font-variant-numeric: tabular-nums;
}
/* Handles */
.file-node__handle {
  width: 8px !important;
  height: 8px !important;
  background: #7c3aed !important;
  border: 2px solid #13131f !important;
  border-radius: 50% !important;
  transition: transform 0.15s ease !important;
}
.file-node__handle:hover {
  transform: scale(1.4) !important;
}
7. frontend/src/components/SidePanel.jsx (Modify)
jsx
/**
 * SidePanel.jsx – Collapsible right panel for selected-file details + AI summary.
 *
 * Security: Escapes details rendering via React JSX text content interpolation.
 */
import { X, FileCode2, Hash, Tag, Sparkles, ChevronRight, RefreshCw, Zap, Flame } from 'lucide-react';
import './SidePanel.css';
const LANG_LABELS = {
  python:     'Python',
  c:          'C',
  cpp:        'C++',
  c_header:   'C Header',
  cpp_header: 'C++ Header',
  javascript: 'JavaScript',
  typescript: 'TypeScript',
  java:       'Java',
  go:         'Go',
  rust:       'Rust',
  ruby:       'Ruby',
  php:        'PHP',
  csharp:     'C#',
  kotlin:     'Kotlin',
  swift:      'Swift',
  shell:      'Shell',
  markdown:   'Markdown',
  json:       'JSON',
  yaml:       'YAML',
  toml:       'TOML',
  xml:        'XML',
  html:       'HTML',
  css:        'CSS',
};
export default function SidePanel({
  isOpen,
  onClose,
  fileData,
  aiSummary,
  aiLoading,
  aiError,
  onRetry,
}) {
  return (
    <>
      <button
        id="side-panel-toggle"
        className={`panel-tab ${isOpen ? 'panel-tab--open' : ''}`}
        onClick={onClose}
        aria-label={isOpen ? 'Collapse panel' : 'Expand panel'}
        title={isOpen ? 'Collapse panel' : 'Expand panel'}
      >
        <ChevronRight
          size={16}
          strokeWidth={2}
          style={{
            transform:  isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.3s ease',
          }}
        />
      </button>
      <aside
        className={`side-panel ${isOpen ? 'side-panel--open' : ''}`}
        aria-label="File details panel"
        role="complementary"
      >
        <div className="panel-header">
          <div className="panel-header__title">
            <FileCode2 size={15} strokeWidth={1.8} className="panel-header__icon" />
            <span>File Inspector</span>
          </div>
          <button
            id="side-panel-close"
            className="panel-close-btn"
            onClick={onClose}
            aria-label="Close panel"
          >
            <X size={14} strokeWidth={2.5} />
          </button>
        </div>
        <div className="panel-body">
          {fileData ? (
            <>
              {/* File path */}
              <section className="panel-section">
                <div className="panel-section__label">
                  <Hash size={11} strokeWidth={2.5} />
                  <span>Path</span>
                </div>
                <p
                  className="panel-section__value panel-section__value--mono truncate"
                  title={fileData.path}
                >
                  {fileData.path}
                </p>
              </section>
              {/* Stats row */}
              <div className="panel-stats-row">
                <div className="panel-stat">
                  <div className="panel-section__label">
                    <Tag size={11} strokeWidth={2.5} />
                    <span>Language</span>
                  </div>
                  <p className="panel-stat__value">
                    {LANG_LABELS[fileData.fileType] ?? fileData.fileType}
                  </p>
                </div>
                <div className="panel-stat">
                  <div className="panel-section__label">
                    <Hash size={11} strokeWidth={2.5} />
                    <span>Lines of Code</span>
                  </div>
                  <p className="panel-stat__value panel-stat__value--accent">
                    {fileData.loc.toLocaleString()}
                  </p>
                </div>
              </div>
              {/* Churn Hotspot Section */}
              <div className="panel-stat" style={{ background: fileData.churn >= 10 ? 'rgba(249, 115, 22, 0.08)' : undefined, borderColor: fileData.churn >= 10 ? 'rgba(249, 115, 22, 0.25)' : undefined }}>
                <div className="panel-section__label">
                  <Flame size={11} style={{ color: fileData.churn >= 10 ? '#f97316' : '#555575' }} />
                  <span>Git Modifications</span>
                </div>
                <p className="panel-stat__value" style={{ color: fileData.churn >= 10 ? '#f97316' : undefined }}>
                  {fileData.churn ?? 0} {fileData.churn === 1 ? 'commit' : 'commits'}
                </p>
              </div>
              <div className="panel-divider" />
              {/* AI Section */}
              <section className="panel-section panel-ai">
                <div className="panel-section__label panel-ai__label">
                  <Sparkles size={12} strokeWidth={2} />
                  <span>AI Summary</span>
                  {aiSummary?.cached && (
                    <span className="panel-ai__badge panel-ai__badge--cached">
                      <Zap size={9} strokeWidth={2.5} />
                      cached
                    </span>
                  )}
                  {!aiSummary && !aiLoading && !aiError && (
                    <span className="panel-ai__badge">powered by Gemini</span>
                  )}
                </div>
                {aiLoading && (
                  <div className="panel-ai__placeholder" aria-label="Loading AI summary" aria-busy="true">
                    <div className="panel-ai__shimmer" />
                    <div className="panel-ai__shimmer panel-ai__shimmer--medium" />
                    <div className="panel-ai__shimmer panel-ai__shimmer--short" />
                  </div>
                )}
                {!aiLoading && aiError && (
                  <div className="panel-ai__error" role="alert">
                    <p className="panel-ai__error-text">{aiError}</p>
                    <button
                      id="ai-retry-button"
                      className="panel-ai__retry-btn"
                      onClick={onRetry}
                      aria-label="Retry AI summary"
                    >
                      <RefreshCw size={11} strokeWidth={2.5} />
                      <span>Retry</span>
                    </button>
                  </div>
                )}
                {!aiLoading && !aiError && aiSummary && (
                  <div className="panel-ai__result">
                    <p className="panel-ai__summary-text">{aiSummary.text}</p>
                    <p className="panel-ai__sha" title={`Content hash: ${aiSummary.sha256}`}>
                      sha256: {aiSummary.sha256.slice(0, 12)}…
                    </p>
                  </div>
                )}
                {!aiLoading && !aiError && !aiSummary && (
                  <div className="panel-ai__placeholder">
                    <div className="panel-ai__shimmer" style={{ opacity: 0.12 }} />
                    <div className="panel-ai__shimmer panel-ai__shimmer--medium" style={{ opacity: 0.08 }} />
                    <p className="panel-ai__hint">
                      An AI-generated explanation of this file will appear here.
                    </p>
                  </div>
                )}
              </section>
            </>
          ) : (
            <div className="panel-empty">
              <FileCode2 size={36} strokeWidth={1} className="panel-empty__icon" />
              <p className="panel-empty__title">No file selected</p>
              <p className="panel-empty__hint">
                Click any node on the canvas to inspect its details.
              </p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
8. frontend/src/components/DirectoryNode.jsx (Create New)
jsx
/**
 * DirectoryNode.jsx – Custom React Flow group node representing a directory bounding box.
 *
 * Security: Escapes folder labels via React JSX text content rendering.
 */
import { memo } from 'react';
import { Folder } from 'lucide-react';
import './DirectoryNode.css';
const DirectoryNode = memo(({ data }) => {
  return (
    <div className="directory-node">
      {/* Visual directory title badge */}
      <div className="directory-node__header">
        <Folder size={13} className="directory-node__icon" />
        <span className="directory-node__label truncate" title={data.label}>
          {data.label}
        </span>
      </div>
    </div>
  );
});
DirectoryNode.displayName = 'DirectoryNode';
export default DirectoryNode;
9. frontend/src/components/DirectoryNode.css (Create New)
css
/* DirectoryNode.css */
.directory-node {
  width: 100%;
  height: 100%;
  border: 1.5px dashed rgba(124, 58, 237, 0.22);
  border-radius: 12px;
  background: rgba(13, 13, 26, 0.12);
  backdrop-filter: blur(4px);
  pointer-events: none; /* Allows canvas clicks to pass through to child nodes */
  position: relative;
  transition: border-color 0.25s ease, background-color 0.25s ease;
}
.directory-node__header {
  position: absolute;
  top: -12px;
  left: 14px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: #151528;
  border: 1px solid rgba(124, 58, 237, 0.35);
  border-radius: 6px;
  padding: 2px 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  color: #c084fc;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
  pointer-events: auto; /* Re-enables interaction on the header label itself */
  z-index: 10;
}
.directory-node__icon {
  color: #a855f7;
  flex-shrink: 0;
}
/* Bounding box hover highlights */
.directory-node:hover {
  border-color: rgba(168, 85, 247, 0.45);
  background: rgba(124, 58, 237, 0.04);
}