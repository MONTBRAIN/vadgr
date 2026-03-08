import { useParams, useNavigate } from 'react-router-dom';
import { useRun, useCancelRun } from '../hooks/useRuns';
import { useAgent } from '../hooks/useAgents';
import { useRunWebSocket } from '../hooks/useWebSocket';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';
import { RunTimeline } from '../components/runs/RunTimeline';
import { RunLog } from '../components/runs/RunLog';

export function RunViewer() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: run, isLoading } = useRun(id ?? '');
  const { data: agent } = useAgent(run?.agent_id ?? '');
  const cancelRun = useCancelRun();
  const { events } = useRunWebSocket(id);

  if (isLoading) return <div className="text-sm text-text-muted">Loading...</div>;
  if (!run) return <div className="text-sm text-text-muted">Run not found.</div>;

  const isActive = run.status === 'running' || run.status === 'queued';
  const canCancel = isActive;

  const handleCancel = async () => {
    if (id) await cancelRun.mutateAsync(id);
  };

  const handleRerun = () => {
    if (run.agent_id) navigate(`/agents/${run.agent_id}`);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-text-primary">Run Viewer</h1>
          {agent && (
            <span className="text-sm text-text-secondary">{agent.name}</span>
          )}
          <span className="text-xs text-text-muted font-mono">#{run.id.slice(0, 8)}</span>
        </div>
        <StatusBadge status={run.status} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
        {/* Left: Timeline */}
        <Card className="p-4">
          <h2 className="text-sm font-medium text-text-primary mb-3">Execution Steps</h2>
          <RunTimeline events={events} />
        </Card>

        {/* Right: Output */}
        <Card className="p-4">
          <h2 className="text-sm font-medium text-text-primary mb-3">Step Output</h2>
          <RunLog events={events} outputs={run.outputs} />
        </Card>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        {canCancel && (
          <Button variant="danger" onClick={handleCancel} disabled={cancelRun.isPending}>
            Cancel Run
          </Button>
        )}
        <Button variant="secondary" onClick={handleRerun}>Re-run</Button>
        {run.status === 'completed' && Object.keys(run.outputs).length > 0 && (
          <Button
            variant="secondary"
            onClick={() => {
              const blob = new Blob([JSON.stringify(run.outputs, null, 2)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `run-${run.id.slice(0, 8)}-outputs.json`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download Outputs
          </Button>
        )}
      </div>
    </div>
  );
}
