import { useNavigate } from 'react-router-dom';
import { Card } from '../ui/Card';
import { StatusBadge, ProviderBadge } from '../ui/Badge';
import { PixelRobot, PixelPlay } from '../ui/PixelIcon';
import { Button } from '../ui/Button';
import type { Agent } from '../../types';

export function AgentCard({ agent }: { agent: Agent }) {
  const navigate = useNavigate();

  return (
    <Card
      hoverable
      className="px-7 py-6 flex flex-col gap-3.5"
      onClick={() => navigate(`/agents/${agent.id}`)}
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-heading text-base font-semibold text-text-primary mb-1.5">{agent.name}</h3>
          <div className="flex gap-2 items-center">
            <StatusBadge status={agent.status} />
            <span className="font-body text-[10px] font-semibold uppercase tracking-wider text-accent">{agent.type}</span>
          </div>
        </div>
        <PixelRobot size={20} color="var(--color-accent)" hole="var(--color-bg-primary)" />
      </div>
      <p className="font-body text-xs text-text-muted font-light leading-relaxed flex-1">
        {agent.description || 'No description'}
      </p>
      <div className="flex items-center justify-between pt-3 border-t border-border">
        <ProviderBadge provider={agent.provider} />
        <Button
          size="sm"
          disabled={agent.status !== 'ready'}
          onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}`); }}
        >
          <PixelPlay size={10} color="var(--color-bg-primary)" /> Run
        </Button>
      </div>
    </Card>
  );
}
