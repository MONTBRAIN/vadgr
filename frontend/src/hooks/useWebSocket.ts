import { useEffect, useRef, useState, useCallback } from 'react';
import type { WSEvent } from '../types';
import { runsApi } from '../api/runs';

export function useRunWebSocket(runId: string | undefined) {
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const lastPersistedTs = useRef<string>('');

  // Load persisted logs on mount
  useEffect(() => {
    if (!runId) return;
    runsApi.getLogs(runId).then((persisted) => {
      if (persisted.length > 0) {
        setEvents(persisted);
        lastPersistedTs.current = persisted[persisted.length - 1].timestamp;
      }
    }).catch(() => {
      // Endpoint may not exist yet or run has no logs
    });
  }, [runId]);

  // WebSocket for live events
  useEffect(() => {
    if (!runId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use relative path -- Vite proxy handles /api/ws in dev (ws: true),
    // same-origin serves it in production. No hardcoded ports needed.
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/api/ws/runs/${runId}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WSEvent;
        // Skip events we already have from persisted logs
        if (lastPersistedTs.current && event.timestamp <= lastPersistedTs.current) return;
        setEvents((prev) => [...prev, event]);
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  const send = useCallback((msg: Record<string, unknown>) => {
    wsRef.current?.send(JSON.stringify(msg));
  }, []);

  return { events, connected, send };
}
