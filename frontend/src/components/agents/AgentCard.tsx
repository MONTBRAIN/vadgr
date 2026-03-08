import { useNavigate } from 'react-router-dom';
import { Card } from '../ui/Card';
import { StatusBadge } from '../ui/Badge';
import type { Agent } from '../../types';

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function AgentCard({ agent }: { agent: Agent }) {
  const navigate = useNavigate();

  return (
    <Card
      hoverable
      className="p-5 flex flex-col gap-3"
      onClick={() => navigate(`/agents/${agent.id}`)}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium text-text-primary truncate">{agent.name}</h3>
        <StatusBadge status={agent.status} />
      </div>
      <p className="text-xs text-text-secondary line-clamp-2 flex-1">
        {agent.description || 'No description'}
      </p>
      <div className="flex items-center justify-between text-xs text-text-muted">
        <span className="capitalize">{agent.provider}</span>
        <span>{timeAgo(agent.created_at)}</span>
      </div>
    </Card>
  );
}
