/**
 * useAiSummary.js – Hook that fetches an AI explanation for a single file.
 *
 * Security:
 * - filepath and scanRoot are sent as JSON body over the Vite dev-proxy
 *   (localhost only). No credentials are transmitted.
 * - Error detail is stored as a plain string — never injected as HTML.
 * - TODO(security): Add request auth headers before production deployment.
 */
import { useState, useCallback, useRef } from 'react';
import axios from 'axios';

/**
 * @typedef {{ text: string, sha256: string, cached: boolean }} AiResult
 *
 * @returns {{
 *   summary:   AiResult | null,
 *   loading:   boolean,
 *   error:     string | null,
 *   fetchSummary: (filepath: string, scanRoot: string) => void,
 *   reset:     () => void,
 * }}
 */
export function useAiSummary() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  // AbortController ref so we can cancel in-flight requests when the user
  // clicks a different node before the previous request completes.
  const abortRef = useRef(null);

  const reset = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setSummary(null);
    setLoading(false);
    setError(null);
  }, []);

  const fetchSummary = useCallback(async (filepath, scanRoot) => {
    if (!filepath || !scanRoot) return;

    // Cancel any prior in-flight request.
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setSummary(null);
    setError(null);
    setLoading(true);

    try {
      const response = await axios.post(
        '/api/explain',
        { filepath, scan_root: scanRoot },
        {
          signal: controller.signal,
          headers: { 'Content-Type': 'application/json' },
        }
      );

      // Guard against a stale response arriving after the component unmounted
      // or the user selected a different node.
      if (!controller.signal.aborted) {
        setSummary({
          text:   String(response.data.summary ?? ''),
          sha256: String(response.data.sha256  ?? ''),
          cached: Boolean(response.data.cached),
        });
      }
    } catch (err) {
      if (axios.isCancel(err) || err?.code === 'ERR_CANCELED') {
        // Silently ignore aborted requests — not a real error.
        return;
      }
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'Failed to load AI summary.';
      setError(String(detail));
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, []);

  return { summary, loading, error, fetchSummary, reset };
}
