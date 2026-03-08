import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRuns } from '../hooks/useRuns';
import { useAgents } from '../hooks/useAgents';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';

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

const statusFilters = ['all', 'queued', 'running', 'completed', 'failed'] as const;

export function RunList() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<string>('all');
  const { data: runs = [], isLoading } = useRuns(filter === 'all' ? undefined : filter);
  const { data: agents = [] } = useAgents();

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-text-primary">Runs</h1>

      <div className="flex items-center gap-2">
        {statusFilters.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-colors cursor-pointer ${
              filter === s
                ? 'bg-accent/15 text-accent'
                : 'text-text-muted hover:text-text-secondary hover:bg-bg-tertiary'
            }`}
          >
            {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-sm text-text-muted">Loading...</div>
      ) : runs.length > 0 ? (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Run ID</th>
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Agent</th>
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Status</th>
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const agent = agents.find((a) => a.id === run.agent_id);
                return (
                  <tr
                    key={run.id}
                    className="border-b border-border/50 hover:bg-bg-tertiary/30 cursor-pointer transition-colors"
                    onClick={() => navigate(`/runs/${run.id}`)}
                  >
                    <td className="py-3 px-4 text-text-muted font-mono text-xs">#{run.id.slice(0, 8)}</td>
                    <td className="py-3 px-4 text-text-primary">{agent?.name ?? '--'}</td>
                    <td className="py-3 px-4"><StatusBadge status={run.status} /></td>
                    <td className="py-3 px-4 text-text-muted">{timeAgo(run.started_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      ) : (
        <Card className="p-12 text-center">
          <p className="text-sm text-text-muted">
            {filter === 'all' ? 'No runs yet. Run an agent to get started.' : `No ${filter} runs.`}
          </p>
        </Card>
      )}
    </div>
  );
}
