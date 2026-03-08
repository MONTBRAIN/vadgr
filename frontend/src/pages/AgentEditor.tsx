import { useParams } from 'react-router-dom';
import { useAgent } from '../hooks/useAgents';
import { AgentForm } from '../components/agents/AgentForm';

export function AgentEditor() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === 'new';
  const { data: agent, isLoading } = useAgent(isNew ? '' : id);

  if (!isNew && isLoading) {
    return <div className="text-sm text-text-muted">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-text-primary">
        {isNew ? 'Create Agent' : `Edit: ${agent?.name ?? ''}`}
      </h1>
      <AgentForm agent={isNew ? undefined : agent} />
    </div>
  );
}
