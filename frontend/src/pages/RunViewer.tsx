import { useParams, useNavigate } from 'react-router-dom';
import { useRun, useCancelRun } from '../hooks/useRuns';
import { useAgent } from '../hooks/useAgents';
import { useRunWebSocket } from '../hooks/useWebSocket';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';
import { RunTimeline } from '../components/runs/RunTimeline';
import { RunLog } from '../components/runs/RunLog';
import { PixelBack, PixelStep, PixelTerminal } from '../components/ui/PixelIcon';

function duration(start: string | null, end: string | null): string {
  if (!start || !end) return '-';
  const s = Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function RunViewer() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: run, isLoading } = useRun(id ?? '');
  const { data: agent } = useAgent(run?.agent_id ?? '');
  const cancelRun = useCancelRun();
  const { events } = useRunWebSocket(id);

  if (isLoading) return <div className="text-sm text-text-muted p-10">Loading...</div>;
  if (!run) return <div className="text-sm text-text-muted p-10">Run not found.</div>;

  const isActive = run.status === 'running' || run.status === 'queued';

  const handleCancel = async () => {
    if (id) await cancelRun.mutateAsync(id);
  };

  return (
    <div>
      <div
        onClick={() => navigate('/runs')}
        className="inline-flex items-center gap-1.5 mb-5 cursor-pointer font-body text-xs text-text-muted hover:text-text-primary transition-colors"
      >
        <PixelBack size={12} color="var(--color-text-muted)" /> Back to Runs
      </div>

      <div className="flex items-start justify-between mb-7">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
            <h1 className="font-heading text-[28px] font-semibold text-text-primary tracking-tight">
              {run.id.slice(0, 8)}
            </h1>
            <StatusBadge status={run.status} />
          </div>
          <p className="font-body text-[13px] text-text-muted font-light">
            Agent: {agent ? (
              <span
                onClick={() => navigate(`/agents/${run.agent_id}`)}
                className="text-accent cursor-pointer font-medium hover:underline"
              >
                {agent.name}
              </span>
            ) : '--'}
          </p>
        </div>
      </div>

      {/* Metadata cards */}
      <div className="grid grid-cols-4 gap-4 mb-7">
        {[
          ['Provider', run.provider ?? '-', true],
          ['Model', run.model ?? '-', true],
          ['Started', run.started_at ? new Date(run.started_at).toLocaleString() : '-', false],
          ['Duration', duration(run.started_at, run.completed_at), false],
        ].map(([label, val, mono]) => (
          <Card key={label as string} className="px-5 py-4">
            <p className="font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">{label as string}</p>
            <p className={`${mono ? 'font-mono' : 'font-body'} text-[13px] text-text-primary`}>{val as string}</p>
          </Card>
        ))}
      </div>

      {/* Execution Log */}
      <Card className="px-7 py-6 mb-7">
        <div className="flex items-center gap-2.5 mb-4">
          <PixelStep size={16} color="var(--color-info)" />
          <h2 className="font-heading text-lg font-semibold text-text-primary">Execution Log</h2>
        </div>
        <RunTimeline events={events} isRunning={isActive} />
        <RunLog events={events} outputs={run.outputs} />
      </Card>

      {/* Outputs — only shown when run has actual output data */}
      {run.outputs && Object.keys(run.outputs).length > 0 && (
        <OutputsCard outputs={run.outputs} runId={run.id} />
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        {isActive && (
          <Button variant="danger" onClick={handleCancel} disabled={cancelRun.isPending}>
            Cancel Run
          </Button>
        )}
        <Button variant="secondary" onClick={() => run.agent_id && navigate(`/agents/${run.agent_id}`)}>Re-run</Button>
      </div>
    </div>
  );
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function downloadOutput(runId: string, fieldName: string) {
  try {
    const { runsApi } = await import('../api/runs');
    const response = await runsApi.getOutput(runId, fieldName);
    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') ?? '';
    const filenameMatch = disposition.match(/filename="([^"]+)"/);
    const filename = filenameMatch?.[1] ?? `${runId.slice(0, 8)}_${fieldName}`;
    downloadBlob(filename, blob);
  } catch {
    downloadBlob(`${runId.slice(0, 8)}_${fieldName}.txt`, new Blob([fieldName], { type: 'text/plain;charset=utf-8' }));
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function OutputsCard({ outputs, runId }: { outputs: Record<string, unknown>; runId: string }) {
  const entries = Object.entries(outputs).map(([key, value]) => {
    const text = typeof value === 'string'
      ? value
      : value && typeof value === 'object' && 'filename' in value
        ? String((value as { filename?: string }).filename ?? key)
        : JSON.stringify(value, null, 2);
    return { key, text, size: new Blob([text]).size };
  });

  return (
    <Card className="px-7 py-6 mb-7">
      <div className="flex items-center gap-2.5 mb-5">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <rect x="1" y="3" width="14" height="10" rx="1.5" stroke="var(--color-accent)" strokeWidth="1.3"/>
          <path d="M5 6l-2 2.5L5 11" stroke="var(--color-accent)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M8 7.5h5M10 9.5h3" stroke="var(--color-accent)" strokeWidth="1" strokeLinecap="round"/>
        </svg>
        <h2 className="font-heading text-lg font-semibold text-text-primary">Output Files</h2>
        <span className="font-mono text-[10px] text-text-muted">{entries.length} {entries.length === 1 ? 'file' : 'files'}</span>
      </div>

      <div className={`grid gap-4 ${entries.length === 1 ? 'grid-cols-1' : entries.length === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
        {entries.map(({ key, text, size }, i) => (
          <div
            key={key}
            className="group flex items-center gap-4 px-5 py-4 bg-hover-bg rounded-[12px] border border-border hover:border-accent/30 transition-colors"
          >
            <div className={`w-10 h-10 rounded-[8px] flex items-center justify-center shrink-0 ${
              i % 3 === 0 ? 'bg-accent/10 border border-accent/20' :
              i % 3 === 1 ? 'bg-success/10 border border-success/20' :
              'bg-info/10 border border-info/20'
            }`}>
              <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke={
                i % 3 === 0 ? 'var(--color-accent)' :
                i % 3 === 1 ? 'var(--color-success)' :
                'var(--color-info)'
              } strokeWidth="1.2">
                <path d="M4 1.5h5.5L13 5v9.5a1 1 0 01-1 1H4a1 1 0 01-1-1v-13a1 1 0 011-1z"/>
                <path d="M9 1.5V5.5h4"/>
                <path d="M5.5 8h5M5.5 10h5M5.5 12h3" strokeLinecap="round"/>
              </svg>
            </div>

            <div className="min-w-0 flex-1">
              <p className="font-body text-sm font-medium text-text-primary truncate">{key}</p>
              <p className="font-mono text-[10px] text-text-muted">{formatBytes(size)}</p>
            </div>

            <button
              onClick={() => downloadOutput(runId, key)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-accent/10 text-accent border border-accent/20 font-body text-[11px] font-medium hover:bg-accent/20 transition-colors cursor-pointer shrink-0"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M8 2v9M4.5 7.5L8 11l3.5-3.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2.5 13h11" strokeLinecap="round"/>
              </svg>
              Download
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}
