/**
 * SidePanel.jsx – Collapsible right panel for selected-file details + AI summary.
 *
 * Security: Escapes details rendering via React JSX text content interpolation.
 */
import { X, FileCode2, Hash, Tag, Sparkles, ChevronRight, RefreshCw, Zap, Flame } from 'lucide-react';
import './SidePanel.css';

const LANG_LABELS = {
  python:     'Python',
  c:          'C',
  cpp:        'C++',
  c_header:   'C Header',
  cpp_header: 'C++ Header',
  javascript: 'JavaScript',
  typescript: 'TypeScript',
  java:       'Java',
  go:         'Go',
  rust:       'Rust',
  ruby:       'Ruby',
  php:        'PHP',
  csharp:     'C#',
  kotlin:     'Kotlin',
  swift:      'Swift',
  shell:      'Shell',
  markdown:   'Markdown',
  json:       'JSON',
  yaml:       'YAML',
  toml:       'TOML',
  xml:        'XML',
  html:       'HTML',
  css:        'CSS',
};

export default function SidePanel({
  isOpen,
  onClose,
  fileData,
  aiSummary,
  aiLoading,
  aiError,
  onRetry,
}) {
  return (
    <>
      <button
        id="side-panel-toggle"
        className={`panel-tab ${isOpen ? 'panel-tab--open' : ''}`}
        onClick={onClose}
        aria-label={isOpen ? 'Collapse panel' : 'Expand panel'}
        title={isOpen ? 'Collapse panel' : 'Expand panel'}
      >
        <ChevronRight
          size={16}
          strokeWidth={2}
          style={{
            transform:  isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.3s ease',
          }}
        />
      </button>

      <aside
        className={`side-panel ${isOpen ? 'side-panel--open' : ''}`}
        aria-label="File details panel"
        role="complementary"
      >
        <div className="panel-header">
          <div className="panel-header__title">
            <FileCode2 size={15} strokeWidth={1.8} className="panel-header__icon" />
            <span>File Inspector</span>
          </div>
          <button
            id="side-panel-close"
            className="panel-close-btn"
            onClick={onClose}
            aria-label="Close panel"
          >
            <X size={14} strokeWidth={2.5} />
          </button>
        </div>

        <div className="panel-body">
          {fileData ? (
            <>
              {/* File path */}
              <section className="panel-section">
                <div className="panel-section__label">
                  <Hash size={11} strokeWidth={2.5} />
                  <span>Path</span>
                </div>
                <p
                  className="panel-section__value panel-section__value--mono truncate"
                  title={fileData.path}
                >
                  {fileData.path}
                </p>
              </section>

              {/* Stats row */}
              <div className="panel-stats-row">
                <div className="panel-stat">
                  <div className="panel-section__label">
                    <Tag size={11} strokeWidth={2.5} />
                    <span>Language</span>
                  </div>
                  <p className="panel-stat__value">
                    {LANG_LABELS[fileData.fileType] ?? fileData.fileType}
                  </p>
                </div>
                <div className="panel-stat">
                  <div className="panel-section__label">
                    <Hash size={11} strokeWidth={2.5} />
                    <span>Lines of Code</span>
                  </div>
                  <p className="panel-stat__value panel-stat__value--accent">
                    {fileData.loc.toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Churn Hotspot Section */}
              <div className="panel-stat" style={{ background: fileData.churn >= 10 ? 'rgba(249, 115, 22, 0.08)' : undefined, borderColor: fileData.churn >= 10 ? 'rgba(249, 115, 22, 0.25)' : undefined }}>
                <div className="panel-section__label">
                  <Flame size={11} style={{ color: fileData.churn >= 10 ? '#f97316' : '#555575' }} />
                  <span>Git Modifications</span>
                </div>
                <p className="panel-stat__value" style={{ color: fileData.churn >= 10 ? '#f97316' : undefined }}>
                  {fileData.churn ?? 0} {fileData.churn === 1 ? 'commit' : 'commits'}
                </p>
              </div>

              <div className="panel-divider" />

              {/* AI Section */}
              <section className="panel-section panel-ai">
                <div className="panel-section__label panel-ai__label">
                  <Sparkles size={12} strokeWidth={2} />
                  <span>AI Summary</span>
                  {aiSummary?.cached && (
                    <span className="panel-ai__badge panel-ai__badge--cached">
                      <Zap size={9} strokeWidth={2.5} />
                      cached
                    </span>
                  )}
                  {!aiSummary && !aiLoading && !aiError && (
                    <span className="panel-ai__badge">powered by Gemini</span>
                  )}
                </div>

                {aiLoading && (
                  <div className="panel-ai__placeholder" aria-label="Loading AI summary" aria-busy="true">
                    <div className="panel-ai__shimmer" />
                    <div className="panel-ai__shimmer panel-ai__shimmer--medium" />
                    <div className="panel-ai__shimmer panel-ai__shimmer--short" />
                  </div>
                )}

                {!aiLoading && aiError && (
                  <div className="panel-ai__error" role="alert">
                    <p className="panel-ai__error-text">{aiError}</p>
                    <button
                      id="ai-retry-button"
                      className="panel-ai__retry-btn"
                      onClick={onRetry}
                      aria-label="Retry AI summary"
                    >
                      <RefreshCw size={11} strokeWidth={2.5} />
                      <span>Retry</span>
                    </button>
                  </div>
                )}

                {!aiLoading && !aiError && aiSummary && (
                  <div className="panel-ai__result">
                    <p className="panel-ai__summary-text">{aiSummary.text}</p>
                    <p className="panel-ai__sha" title={`Content hash: ${aiSummary.sha256}`}>
                      sha256: {aiSummary.sha256.slice(0, 12)}…
                    </p>
                  </div>
                )}

                {!aiLoading && !aiError && !aiSummary && (
                  <div className="panel-ai__placeholder">
                    <div className="panel-ai__shimmer" style={{ opacity: 0.12 }} />
                    <div className="panel-ai__shimmer panel-ai__shimmer--medium" style={{ opacity: 0.08 }} />
                    <p className="panel-ai__hint">
                      An AI-generated explanation of this file will appear here.
                    </p>
                  </div>
                )}
              </section>
            </>
          ) : (
            <div className="panel-empty">
              <FileCode2 size={36} strokeWidth={1} className="panel-empty__icon" />
              <p className="panel-empty__title">No file selected</p>
              <p className="panel-empty__hint">
                Click any node on the canvas to inspect its details.
              </p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}