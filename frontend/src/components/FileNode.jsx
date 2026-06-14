/**
 * FileNode.jsx – Custom React Flow node for a single source file.
 *
 * Security: All text is rendered via React JSX (textContent equivalent),
 * never via dangerouslySetInnerHTML.
 */
import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import './FileNode.css';

/** Map file-type strings → badge colour token */
const TYPE_COLOUR = {
  python:      '#a78bfa',  /* violet  */
  c:           '#fb923c',  /* orange  */
  cpp:         '#f97316',
  c_header:    '#fdba74',
  cpp_header:  '#fcd34d',
  javascript:  '#facc15',  /* yellow  */
  typescript:  '#38bdf8',  /* sky     */
  java:        '#4ade80',  /* green   */
  go:          '#22d3ee',  /* cyan    */
  rust:        '#fb7185',  /* rose    */
  ruby:        '#f43f5e',
  php:         '#818cf8',  /* indigo  */
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

  return (
    <div className={`file-node ${selected ? 'file-node--selected' : ''}`}>
      <Handle type="target" position={Position.Left}  className="file-node__handle" />
      <Handle type="source" position={Position.Right} className="file-node__handle" />

      {/* Accent stripe */}
      <span className="file-node__stripe" style={{ background: colour }} />

      <div className="file-node__body">
        <span className="file-node__label truncate" title={data.label}>
          {data.label}
        </span>
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
