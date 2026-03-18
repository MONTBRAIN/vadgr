import { useNavigate } from 'react-router-dom';
import { useAgents } from '../hooks/useAgents';
import { useRuns } from '../hooks/useRuns';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge, ProviderBadge } from '../components/ui/Badge';
import { PixelRobot, PixelPlay, PixelCheck, PixelX } from '../components/ui/PixelIcon';

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '--';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function duration(start: string | null, end: string | null): string {
  if (!start || !end) return '-';
  const s = Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function Dashboard() {
  const navigate = useNavigate();
  const { data: agents = [], isLoading: agentsLoading } = useAgents();
  const { data: runs = [], isLoading: runsLoading } = useRuns();

  const totalAgents = agents.length;
  const activeRuns = runs.filter((r) => r.status === 'running' || r.status === 'queued').length;
  const completedRuns = runs.filter((r) => r.status === 'completed').length;
  const failedRuns = runs.filter((r) => r.status === 'failed').length;

  const metrics = [
    { label: 'Total Agents', value: totalAgents, colorClass: 'text-accent', icon: <PixelRobot size={28} color="var(--color-accent)" hole="var(--color-bg-primary)" /> },
    { label: 'Active Runs', value: activeRuns, colorClass: 'text-info', icon: <PixelPlay size={28} color="var(--color-info)" /> },
    { label: 'Completed Runs', value: completedRuns, colorClass: 'text-success', icon: <PixelCheck size={28} color="var(--color-success)" /> },
    { label: 'Failed Runs', value: failedRuns, colorClass: 'text-danger', icon: <PixelX size={28} color="var(--color-danger)" /> },
  ];

  const recentAgents = agents.slice(0, 5);
  const recentRuns = runs.slice(0, 6);

  return (
    <div>
      <div className="mb-8">
        <h1 className="font-heading text-[28px] font-semibold text-text-primary tracking-tight mb-1">Dashboard</h1>
        <p className="font-body text-[13px] text-text-muted font-light">Overview of your AI agent operations</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-4 gap-5 mb-8">
        {metrics.map((m) => (
          <Card key={m.label} className="px-7 py-6 relative overflow-hidden">
            <div className="absolute top-5 right-6 opacity-70">{m.icon}</div>
            <p className="font-body text-[11px] text-text-muted font-medium tracking-wide uppercase mb-3">{m.label}</p>
            <p className={`font-heading text-[32px] font-bold ${m.colorClass} tracking-tight leading-none`}>{m.value}</p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-[1.5fr_1fr] gap-5">
        {/* Recent Agents */}
        <Card className="overflow-hidden">
          <div className="px-7 pt-5 pb-0 flex items-center justify-between mb-3">
            <div className="flex items-center gap-2.5">
              <PixelRobot size={18} color="var(--color-accent)" hole="var(--color-bg-primary)" />
              <h2 className="font-heading text-base font-semibold text-text-primary">Recent Agents</h2>
            </div>
            <span onClick={() => navigate('/agents')} className="font-body text-xs text-text-muted cursor-pointer hover:text-text-primary transition-colors">View all</span>
          </div>
          {agentsLoading ? (
            <div className="p-7 text-sm text-text-muted">Loading...</div>
          ) : recentAgents.length > 0 ? (
            <>
              <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1.2fr] px-7 py-3 border-b border-border">
                {['Name', 'Status', 'Created with', 'Type', 'Last Updated'].map((h) => (
                  <span key={h} className="font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider">{h}</span>
                ))}
              </div>
              {recentAgents.map((agent, i) => (
                <div
                  key={agent.id}
                  className="grid grid-cols-[2fr_1fr_1fr_1fr_1.2fr] px-7 py-3.5 items-center cursor-pointer transition-colors hover:bg-hover-bg"
                  style={{ background: i % 2 === 1 ? 'var(--color-hover-bg)' : 'transparent' }}
                  onClick={() => navigate(`/agents/${agent.id}`)}
                >
                  <span className="font-body text-[13px] text-text-primary">{agent.name}</span>
                  <StatusBadge status={agent.status} />
                  <ProviderBadge provider={agent.provider} label="" />
                  <span className="font-body text-[10px] font-semibold uppercase tracking-wider text-accent">{agent.type}</span>
                  <span className="font-body text-xs text-text-muted font-light">{timeAgo(agent.updated_at)}</span>
                </div>
              ))}
            </>
          ) : (
            <div className="p-8 text-center">
              <p className="text-sm text-text-muted mb-3">No agents yet</p>
              <Button size="sm" onClick={() => navigate('/agents/new')}>Create your first agent</Button>
            </div>
          )}
        </Card>

        {/* Recent Runs */}
        <Card className="overflow-hidden">
          <div className="px-7 pt-5 pb-4 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <PixelPlay size={18} color="var(--color-info)" />
              <h2 className="font-heading text-base font-semibold text-text-primary">Recent Runs</h2>
            </div>
            <span onClick={() => navigate('/runs')} className="font-body text-xs text-text-muted cursor-pointer hover:text-text-primary transition-colors">View all</span>
          </div>
          {runsLoading ? (
            <div className="p-7 text-sm text-text-muted">Loading...</div>
          ) : recentRuns.length > 0 ? (
            recentRuns.map((run) => {
              const agent = agents.find((a) => a.id === run.agent_id);
              return (
                <div
                  key={run.id}
                  className="flex items-center justify-between px-7 py-3.5 border-t border-border/40 cursor-pointer transition-colors hover:bg-hover-bg"
                  onClick={() => navigate(`/runs/${run.id}`)}
                >
                  <div className="flex items-center gap-3">
                    <StatusBadge status={run.status} />
                    <div>
                      <p className="font-body text-[13px] text-text-primary">{agent?.name ?? '--'}</p>
                      <p className="font-body text-[11px] font-light text-text-muted">{duration(run.started_at, run.completed_at)}</p>
                    </div>
                  </div>
                  <span className="font-body text-[11px] text-text-muted font-light">{timeAgo(run.started_at)}</span>
                </div>
              );
            })
          ) : (
            <div className="p-8 text-center">
              <p className="text-sm text-text-muted">No runs yet.</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
