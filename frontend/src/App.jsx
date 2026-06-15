import { useCallback, useState, useLayoutEffect, useEffect, useMemo } from 'react';
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

const NODE_TYPES = {
  fileNode: FileNode,
  directoryNode: DirectoryNode,
};

// Dynamic style classes — must be stripped before re-applying to prevent
// className accumulation when React Flow writes nodes back via onNodesChange.
const NODE_STYLE_CLASSES = new Set(['node-highlighted', 'node-dimmed', 'node-group-transparent']);
const EDGE_STYLE_CLASSES = new Set(['edge-highlighted', 'edge-dimmed']);

function stripNodeClass(cls) {
  if (!cls) return '';
  return cls.split(' ').filter(c => !NODE_STYLE_CLASSES.has(c)).join(' ').trim();
}

function stripEdgeClass(cls) {
  if (!cls) return '';
  return cls.split(' ').filter(c => !EDGE_STYLE_CLASSES.has(c)).join(' ').trim();
}

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
  const [hoveredNode, setHoveredNode]    = useState(null);
  const [rfInstance,  setRfInstance]     = useState(null);

  // Sync React Flow state when a new scan completes.
  // useLayoutEffect runs before paint so there is no flash of empty content.
  useLayoutEffect(() => {
    setNodes(fetchedNodes);
    setEdges(fetchedEdges);
  }, [fetchedNodes, fetchedEdges]);

  // Programmatic fitView — fires only when scan data changes, never on
  // AI-loading re-renders. The 80 ms delay lets React Flow finish its own
  // internal layout pass before we ask it to fit the viewport.
  useEffect(() => {
    if (!rfInstance || fetchedNodes.length === 0) return;
    const id = setTimeout(() => {
      rfInstance.fitView({ padding: 0.08, maxZoom: 1.2 });
    }, 80);
    return () => clearTimeout(id);
  }, [rfInstance, fetchedNodes]);

  // Side panel
  const [panelOpen,    setPanelOpen]    = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);

  const onNodeClick = useCallback((_event, node) => {
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

  const closePanel = useCallback(() => setPanelOpen(false), []);

  const onNodeMouseEnter = useCallback((_event, node) => {
    if (node.type === 'directoryNode') return;
    setHoveredNode(node.id);
  }, []);

  const onNodeMouseLeave = useCallback(() => setHoveredNode(null), []);

  // Highlight sets — only recalculated when hover target or edge list changes.
  const { highlightNodes, highlightEdges } = useMemo(() => {
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

  // Styled nodes — memoized so React Flow only diffs when hover state or the
  // underlying node list actually changes (not on every AI-loading re-render).
  // Previous style classes are stripped first to prevent accumulation.
  const styledNodes = useMemo(() => nodes.map((node) => {
    const baseClass = stripNodeClass(node.className);

    if (!hoveredNode) {
      // Return same reference when nothing changed to help React Flow bail out early.
      return baseClass === (node.className ?? '').trim()
        ? node
        : { ...node, className: baseClass || undefined };
    }

    const isHl  = highlightNodes.has(node.id);
    const isDir = node.type === 'directoryNode';
    const styleClass = isHl
      ? 'node-highlighted'
      : isDir ? 'node-group-transparent' : 'node-dimmed';

    return {
      ...node,
      className: [baseClass, styleClass].filter(Boolean).join(' '),
    };
  }), [nodes, hoveredNode, highlightNodes]);

  // Styled edges — memoized similarly.
  const styledEdges = useMemo(() => edges.map((edge) => {
    const baseClass = stripEdgeClass(edge.className);

    if (!hoveredNode) {
      return { ...edge, animated: false, className: baseClass || undefined };
    }

    const isHl = highlightEdges.has(edge.id);
    return {
      ...edge,
      animated: isHl,
      className: [baseClass, isHl ? 'edge-highlighted' : 'edge-dimmed'].filter(Boolean).join(' '),
    };
  }), [edges, hoveredNode, highlightEdges]);

  const isEmpty = nodes.length === 0 && !loading;

  return (
    <div className="app-shell">
      <div className="canvas-area">
        <ReactFlow
          nodes={styledNodes}
          edges={styledEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onNodeMouseEnter={onNodeMouseEnter}
          onNodeMouseLeave={onNodeMouseLeave}
          onInit={setRfInstance}
          nodeTypes={NODE_TYPES}
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
                {nodes.filter(n => n.type !== 'directoryNode').length} files
                &nbsp;·&nbsp;
                {edges.length} dependencies
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
              Enter a directory path and click <strong>Scan Repository</strong>.
              When running via Docker, your local <code>/home/…</code> paths are
              accessible as <code>/projects/…</code>
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
