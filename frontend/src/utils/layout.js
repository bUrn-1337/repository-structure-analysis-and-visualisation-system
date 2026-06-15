/**
 * Computes graph layout using Dagre with compound directory nodes.
 */
import dagre from '@dagrejs/dagre';

export const NODE_WIDTH  = 220;
export const NODE_HEIGHT =  72;
const DIR_PADDING = 48;

export function applyDagreLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph({ compound: true });
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', ranksep: 100, nodesep: 52, marginx: 20, marginy: 20 });

  nodes.forEach((n) => {
    const isDir = n.type === 'directoryNode';
    g.setNode(n.id, {
      width:  isDir ? 120 : NODE_WIDTH,
      height: isDir ? 120 : NODE_HEIGHT,
    });
  });

  nodes.forEach((n) => {
    if (n.parentId) g.setParent(n.id, n.parentId);
  });

  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  const laidOutNodes = nodes.map((n) => {
    const pos = g.node(n.id);
    const isDir = n.type === 'directoryNode';
    const width  = isDir ? pos.width  + DIR_PADDING : NODE_WIDTH;
    const height = isDir ? pos.height + DIR_PADDING : NODE_HEIGHT;

    let position = {
      x: pos.x - width  / 2,
      y: pos.y - height / 2,
    };

    if (n.parentId) {
      const parentPos = g.node(n.parentId);
      const parentW   = parentPos.width  + DIR_PADDING;
      const parentH   = parentPos.height + DIR_PADDING;
      position = {
        x: position.x - (parentPos.x - parentW / 2),
        y: position.y - (parentPos.y - parentH / 2),
      };
    }

    const nodeData = { ...n, position };
    if (isDir) nodeData.style = { width, height };
    return nodeData;
  });

  return { nodes: laidOutNodes, edges };
}
