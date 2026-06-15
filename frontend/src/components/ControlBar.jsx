/**
 * Control bar component containing the directory input and scan controls.
 */
import { useState } from 'react';
import { FolderSearch, Loader2, AlertCircle, GitFork, Cpu } from 'lucide-react';
import './ControlBar.css';

/**
 * @param {{ onScan: (path: string) => void, loading: boolean, error: string|null }} props
 */
export default function ControlBar({ onScan, loading, error }) {
  const [path, setPath] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onScan(path);
  };

  return (
    <div className="ctrl-bar-wrap" role="banner">
      {/* Brand */}
      <div className="ctrl-bar">
        <div className="ctrl-brand">
          <Cpu size={18} strokeWidth={1.8} className="ctrl-brand__icon" />
          <span className="ctrl-brand__name">RepoScope</span>
        </div>

        <div className="ctrl-divider" aria-hidden="true" />

        {/* Scan form */}
        <form className="ctrl-form" onSubmit={handleSubmit} aria-label="Repository scan form">
          <div className="ctrl-input-wrap">
            <FolderSearch size={15} className="ctrl-input-icon" strokeWidth={1.8} />
            <input
              id="repo-path-input"
              className="ctrl-input"
              type="text"
              placeholder="/projects/my-repo"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              aria-label="Repository path"
              disabled={loading}
              autoComplete="off"
              spellCheck={false}
              title="Enter the path as seen by the server. In Docker, /home/… is mounted at /projects/…"
            />
          </div>

          <button
            id="scan-button"
            className={`ctrl-btn ${loading ? 'ctrl-btn--loading' : ''}`}
            type="submit"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? (
              <>
                <Loader2 size={14} className="spin" strokeWidth={2} />
                <span>Scanning…</span>
              </>
            ) : (
              <>
                <FolderSearch size={14} strokeWidth={2} />
                <span>Scan Repository</span>
              </>
            )}
          </button>
        </form>

        <div className="ctrl-divider" aria-hidden="true" />

        {/* External link */}
        <a
          className="ctrl-icon-btn"
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="GitHub"
        >
          <GitFork size={16} strokeWidth={1.8} />
        </a>
      </div>

      {/* Error banner */}
      {error && (
        <div className="ctrl-error" role="alert" aria-live="polite">
          <AlertCircle size={14} strokeWidth={2} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
