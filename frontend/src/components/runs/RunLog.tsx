import type { WSEvent } from '../../types';

interface RunLogProps {
  events: WSEvent[];
  outputs: Record<string, unknown>;
}

export function RunLog({ events, outputs }: RunLogProps) {
  const logLines = events
    .filter((e) => e.type === 'agent_completed' || e.type === 'run_completed' || e.type === 'run_failed')
    .map((e) => {
      if (e.type === 'run_failed') return `ERROR: ${JSON.stringify(e.data?.error ?? 'Unknown error')}`;
      if (e.type === 'run_completed') return `COMPLETED: ${JSON.stringify(e.data?.outputs ?? {})}`;
      return JSON.stringify(e.data ?? {}, null, 2);
    });

  const hasOutputs = Object.keys(outputs).length > 0;

  return (
    <div className="bg-bg-primary border border-border rounded-lg p-4 font-mono text-xs overflow-auto max-h-[500px]">
      {hasOutputs ? (
        <pre className="text-text-primary whitespace-pre-wrap">
          {JSON.stringify(outputs, null, 2)}
        </pre>
      ) : logLines.length > 0 ? (
        logLines.map((line, i) => (
          <div key={i} className="text-text-secondary py-0.5">{line}</div>
        ))
      ) : (
        <div className="text-text-muted">No output yet.</div>
      )}
    </div>
  );
}
