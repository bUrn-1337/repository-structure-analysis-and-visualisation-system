/**
 * Custom React Flow group node representing a directory bounding box.
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