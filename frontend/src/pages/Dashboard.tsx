import { useNavigate } from 'react-router-dom';
import { useAgents } from '../hooks/useAgents';
import { useRuns } from '../hooks/useRuns';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';
import { AgentCard } from '../components/agents/AgentCard';

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

export function Dashboard() {
  const navigate = useNavigate();
  const { data: agents = [], isLoading: agentsLoading } = useAgents();
  const { data: runs = [], isLoading: runsLoading } = useRuns();

  const recentAgents = agents.slice(0, 3);
  const recentRuns = runs.slice(0, 5);

  const totalAgents = agents.length;
  const activeRuns = runs.filter((r) => r.status === 'running' || r.status === 'queued').length;
  const completedRuns = runs.filter((r) => r.status === 'completed').length;
  const successRate = runs.length > 0 ? Math.round((completedRuns / runs.length) * 100) : 0;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text-primary">Dashboard</h1>
        <Button onClick={() => navigate('/agents/new')}>+ New Agent</Button>
      </div>

      {/* Recent Agents */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-text-secondary">Recent Agents</h2>
        {agentsLoading ? (
          <div className="text-sm text-text-muted">Loading...</div>
        ) : recentAgents.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recentAgents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        ) : (
          <Card className="p-8 text-center">
            <p className="text-sm text-text-muted mb-3">No agents yet</p>
            <Button size="sm" onClick={() => navigate('/agents/new')}>Create your first agent</Button>
          </Card>
        )}
      </section>

      {/* Recent Runs */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-text-secondary">Recent Runs</h2>
        {runsLoading ? (
          <div className="text-sm text-text-muted">Loading...</div>
        ) : recentRuns.length > 0 ? (
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Agent</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Started</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((run) => {
                  const agent = agents.find((a) => a.id === run.agent_id);
                  return (
                    <tr
                      key={run.id}
                      className="border-b border-border/50 hover:bg-bg-tertiary/30 cursor-pointer transition-colors"
                      onClick={() => navigate(`/runs/${run.id}`)}
                    >
                      <td className="py-3 px-4 text-text-primary">{agent?.name ?? run.agent_id ?? '--'}</td>
                      <td className="py-3 px-4"><StatusBadge status={run.status} /></td>
                      <td className="py-3 px-4 text-text-muted">{timeAgo(run.started_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        ) : (
          <Card className="p-8 text-center">
            <p className="text-sm text-text-muted">No runs yet. Create an agent and run it.</p>
          </Card>
        )}
      </section>

      {/* Quick Stats */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-text-secondary">Quick Stats</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Agents" value={totalAgents} />
          <StatCard label="Active Runs" value={activeRuns} />
          <StatCard label="Success Rate" value={`${successRate}%`} />
          <StatCard label="Completed" value={completedRuns} />
        </div>
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="p-4">
      <div className="text-2xl font-semibold text-text-primary">{value}</div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
    </Card>
  );
}
