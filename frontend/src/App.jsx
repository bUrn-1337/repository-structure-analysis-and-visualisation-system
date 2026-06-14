/**
 * App.jsx – Root application component.
 *
 * Layout: full-screen canvas (React Flow) + floating ControlBar +
 *         collapsible SidePanel on the right.
 *
 * Security:
 * - onNodeClick data is plain JS objects from the scan response; no HTML
 *   is injected anywhere in the tree.
 * - TODO(security): Add API authentication headers in useRepositoryScan before
 *   deploying beyond localhost.
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
import './App.css';

/** Register custom node types outside the component to avoid re-registrations */
const NODE_TYPES = { fileNode: FileNode };

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
    const fileRelPath = node.data.path;          // relative path from scan root
    const absFilePath = scanRoot
      ? `${scanRoot}/${fileRelPath}`.replace(/\/+/g, '/')  // join cleanly
      : fileRelPath;

    setSelectedFile({
      path:     fileRelPath,
      absPath:  absFilePath,
      label:    node.data.label,
      loc:      node.data.loc,
      fileType: node.data.fileType,
    });
    setPanelOpen(true);

    // Reset previous AI state immediately so the shimmer shows for the new file,
    // then kick off the fetch.
    resetAiSummary();
    if (scanRoot) {
      fetchAiSummary(absFilePath, scanRoot);
    }
  }, [scanRoot, fetchAiSummary, resetAiSummary]);

  const closePanel = useCallback(() => {
    setPanelOpen(false);
  }, []);

  // Empty-canvas hint
  const isEmpty = nodes.length === 0 && !loading;

  return (
    <div className="app-shell">
      {/* ── React Flow Canvas ─────────────────────────────────────────── */}
      <div className="canvas-area">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.18, maxZoom: 1.4 }}
          minZoom={0.08}
          maxZoom={3}
          proOptions={{ hideAttribution: false }}
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

          {/* Floating stats panel — bottom-left corner */}
          {nodes.length > 0 && (
            <Panel position="bottom-left" className="stats-panel">
              <span className="stats-pill">
                {nodes.length} files &nbsp;·&nbsp; {edges.length} dependencies
              </span>
            </Panel>
          )}
        </ReactFlow>

        {/* Empty canvas illustration */}
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

        {/* Floating ControlBar */}
        <ControlBar onScan={scan} loading={loading} error={error} />
      </div>

      {/* ── Side Panel ────────────────────────────────────────────────── */}
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
