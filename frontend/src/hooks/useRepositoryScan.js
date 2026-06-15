/**
 * Custom hook to scan a repository and fetch the layout nodes and edges.
 */
import { useState, useCallback } from 'react';
import axios from 'axios';
import { applyDagreLayout } from '../utils/layout';

/**
 * Transform the raw API payload into React Flow–ready nodes and edges,
 * applying automatic Dagre layout so nodes are never stacked at (0,0).
 *
 * @param {{ nodes: object[], edges: object[] }} data
 */
function transform(data) {
  const rfNodes = data.nodes.map((n) => ({
    id: n.id,
    type: n.type || 'fileNode',
    parentId: n.parentId,
    data: {
      label:    n.data.label,
      loc:      n.data.loc,
      fileType: n.data.fileType,
      churn:    n.data.churn,
      path:     n.id,
    },
    // Position placeholder — Dagre will overwrite these.
    position: { x: 0, y: 0 },
  }));

  const rfEdges = data.edges.map((e) => ({
    id:           e.id,
    source:       e.source,
    target:       e.target,
    animated:     false,
    style:        { stroke: '#7c3aed', strokeWidth: 2, opacity: 0.55 },
    markerEnd:    { type: 'arrowclosed', color: '#a855f7', width: 16, height: 16 },
  }));

  return applyDagreLayout(rfNodes, rfEdges);
}

/**
 * @returns {{
 *   nodes: import('@xyflow/react').Node[],
 *   edges: import('@xyflow/react').Edge[],
 *   loading: boolean,
 *   error: string | null,
 *   scan: (path: string) => Promise<void>,
 * }}
 */
export function useRepositoryScan() {
  const [nodes,    setNodes]    = useState([]);
  const [edges,    setEdges]    = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);
  // Absolute path of the last successfully-scanned directory. Used by
  // /api/explain as the scan_root boundary for path-traversal protection.
  const [scanRoot, setScanRoot] = useState(null);

  const scan = useCallback(async (path) => {
    if (!path || !path.trim()) {
      setError('Please enter a directory path.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // The Vite dev-proxy forwards /api/* → http://127.0.0.1:8000
      const response = await axios.get('/api/scan', {
        params: { path: path.trim() },
      });

      const { nodes: n, edges: e } = transform(response.data);
      setNodes(n);
      setEdges(e);
      setScanRoot(path.trim()); // persist for /api/explain
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'An unknown error occurred.';
      setError(String(detail));
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { nodes, edges, loading, error, scan, scanRoot };
}
