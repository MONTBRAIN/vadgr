import { useEffect, useRef, useState, useCallback } from 'react';
import type { WSEvent } from '../types';

export function useRunWebSocket(runId: string | undefined) {
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/runs/${runId}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WSEvent;
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
