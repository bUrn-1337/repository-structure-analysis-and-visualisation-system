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