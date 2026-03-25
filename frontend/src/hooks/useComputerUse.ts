/**
 * Module-scoped state for computer use toggle operations.
 *
 * The enable/disable PUT can take 30-60s (venv creation + pip install).
 * If the user navigates away and back, the Settings component remounts
 * and re-fetches status from the backend — which still returns the old
 * state because the PUT hasn't completed. This makes the toggle "reset".
 *
 * This module keeps the in-flight promise outside React component
 * lifecycle so remounts can pick it up instead of re-fetching stale state.
 */

import { api } from '../api/client';

interface CuStatus {
  enabled: boolean;
  cache_enabled: boolean;
}

let inflight: {
  promise: Promise<CuStatus>;
  activating: boolean;
} | null = null;

export function getInflight() {
  return inflight;
}

export function resetInflight() {
  inflight = null;
}

export async function toggleComputerUse(
  enabled: boolean,
  cacheEnabled: boolean,
): Promise<CuStatus> {
  const promise = api.put<CuStatus>('/settings/computer-use', {
    enabled,
    cache_enabled: cacheEnabled,
  });

  inflight = { promise, activating: enabled };

  try {
    const result = await promise;
    return result;
  } finally {
    inflight = null;
  }
}
