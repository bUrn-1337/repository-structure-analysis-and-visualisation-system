/**
 * layout.js – Automatic graph layout using Dagre.
 *
 * Security note: No user input is passed to any system command or eval.
 * All values are numeric/string data derived from the scan result.
 */
import dagre from '@dagrejs/dagre';

const NODE_WIDTH  = 200;
const NODE_HEIGHT =  60;

/**
 * Apply a left-to-right Dagre layout to React Flow nodes + edges.
 * Returns new arrays with `position` filled in on each node.
 *
 * @param {import('@xyflow/react').Node[]} nodes
 * @param {import('@xyflow/react').Edge[]} edges
 * @returns {{ nodes: import('@xyflow/react').Node[], edges: import('@xyflow/react').Edge[] }}
 */
export function applyDagreLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', ranksep: 90, nodesep: 50 });

  nodes.forEach((n) =>
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  );
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  const laidOutNodes = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: laidOutNodes, edges };
}
