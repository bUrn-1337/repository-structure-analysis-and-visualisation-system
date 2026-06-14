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