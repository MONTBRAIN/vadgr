import { useEffect, useRef } from 'react';
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

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

const eventIcons: Record<string, string> = {
  run_started: 'bg-info',
  agent_started: 'bg-info',
  step: 'bg-info',
  agent_completed: 'bg-accent',
  agent_log: 'bg-text-muted/50',
  run_completed: 'bg-accent',
  run_failed: 'bg-danger',
  approval_required: 'bg-warning',
};

interface EventGroup {
  event: WSEvent;
  label: string;
  sublabel?: string;
  logs: WSEvent[];
}

/**
 * Group events into timeline nodes. Step-level agent_log events
 * (those with step_num/step_name in data) get their own node per step.
 * Non-step agent_log events attach to the last node.
 */
function groupEvents(events: WSEvent[]): EventGroup[] {
  const groups: EventGroup[] = [];
  let currentStepKey = '';

  for (const event of events) {
    const stepNum = event.data?.step_num as number | undefined;
    const stepName = event.data?.step_name as string | undefined;

    if (event.type === 'agent_log') {
      const msg = String(event.data?.message ?? '');

      // Step start marker — create a new step node
      if (msg.startsWith('--- Step ') && (msg.includes('[CLI]') || msg.includes('[Desktop]'))) {
        // Parse step info from data fields or fall back to marker text
        const match = msg.match(/^--- Step (\d+): (.+?) \[(CLI|Desktop)\] ---$/);
        const num = stepNum ?? (match ? Number(match[1]) : undefined);
        const name = stepName ?? (match ? match[2] : undefined);
        const stepKey = `step-${num}`;
        if (stepKey !== currentStepKey) {
          currentStepKey = stepKey;
          groups.push({
            event: { ...event, type: 'step' },
            label: `Step ${num}`,
            sublabel: name,
            logs: [],
          });
        }
        continue;
      }

      // Step complete marker — skip it
      if (msg.match(/^--- Step \d+ complete ---$/)) {
        continue;
      }

      // Regular log — attach to current step node or last group
      if (groups.length > 0) {
        groups[groups.length - 1].logs.push(event);
      }
    } else {
      // Non-log event — gets its own node
      currentStepKey = '';
      groups.push({
        event,
        label: event.type.replace(/_/g, ' '),
        sublabel: event.data?.name != null ? String(event.data.name) : undefined,
        logs: [],
      });
    }
  }
  return groups;
}

export function RunTimeline({ events }: RunTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="text-sm text-text-muted py-4">Waiting for execution events...</div>
    );
  }

  const groups = groupEvents(events);

  return (
    <div ref={scrollRef} className="space-y-0 max-h-[500px] overflow-y-auto pr-1">
      {groups.map((group, gi) => (
        <div key={gi}>
          {/* Main event node */}
          <div className="flex items-start gap-3 py-2">
            <div className="flex flex-col items-center mt-1">
              <div className={`w-2.5 h-2.5 rounded-full ${eventIcons[group.event.type] ?? 'bg-text-muted'}`} />
              {(gi < groups.length - 1 || group.logs.length > 0) && (
                <div className="w-px h-6 bg-border mt-1" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-text-primary capitalize">
                  {group.label}
                </span>
                <div className="flex items-center gap-2">
                  {group.event.data?.duration_ms != null && (
                    <span className="text-xs text-text-muted">
                      {formatDuration(group.event.data.duration_ms as number)}
                    </span>
                  )}
                  <span className="text-[10px] text-text-muted/60 font-mono">
                    {formatTime(group.event.timestamp)}
                  </span>
                </div>
              </div>
              {group.sublabel && (
                <span className="text-xs text-text-secondary">{group.sublabel}</span>
              )}
            </div>
          </div>

          {/* Grouped log lines under this event */}
          {group.logs.length > 0 && (
            <div className="ml-[11px] border-l border-border pl-5 pb-1">
              <div className="bg-bg-primary border border-border/60 rounded-md p-2.5 max-h-[180px] overflow-y-auto">
                {group.logs.map((log, li) => (
                  <div key={li} className="flex items-start gap-2 py-0.5">
                    <span className="text-[10px] text-text-muted/50 font-mono shrink-0 mt-px">
                      {formatTime(log.timestamp)}
                    </span>
                    <span className="text-xs text-text-secondary font-mono leading-relaxed">
                      {String(log.data?.message ?? '')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
