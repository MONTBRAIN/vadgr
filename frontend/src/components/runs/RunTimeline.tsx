import type { WSEvent } from '../../types';

interface RunTimelineProps {
  events: WSEvent[];
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

const eventIcons: Record<string, string> = {
  run_started: 'bg-info',
  agent_started: 'bg-info',
  agent_completed: 'bg-accent',
  run_completed: 'bg-accent',
  run_failed: 'bg-danger',
  approval_required: 'bg-warning',
};

export function RunTimeline({ events }: RunTimelineProps) {
  if (events.length === 0) {
    return (
      <div className="text-sm text-text-muted py-4">Waiting for execution events...</div>
    );
  }

  return (
    <div className="space-y-0">
      {events.map((event, i) => (
        <div key={i} className="flex items-start gap-3 py-2">
          <div className="flex flex-col items-center mt-1">
            <div className={`w-2.5 h-2.5 rounded-full ${eventIcons[event.type] ?? 'bg-text-muted'}`} />
            {i < events.length - 1 && <div className="w-px h-6 bg-border mt-1" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-text-primary capitalize">
                {event.type.replace(/_/g, ' ')}
              </span>
              {event.data?.duration_ms != null && (
                <span className="text-xs text-text-muted">
                  {formatDuration(event.data.duration_ms as number)}
                </span>
              )}
            </div>
            {event.data?.name != null && (
              <span className="text-xs text-text-secondary">{String(event.data.name)}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
