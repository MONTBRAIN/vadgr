import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAgents, useDeleteAgent } from '../hooks/useAgents';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';

export function AgentList() {
  const navigate = useNavigate();
  const { data: agents = [], isLoading } = useAgents();
  const deleteAgent = useDeleteAgent();
  const [search, setSearch] = useState('');

  const filtered = agents.filter(
    (a) =>
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.description.toLowerCase().includes(search.toLowerCase()),
  );

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Delete this agent?')) {
      await deleteAgent.mutateAsync(id);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text-primary">Agents</h1>
        <Button onClick={() => navigate('/agents/new')}>+ New Agent</Button>
      </div>

      <input
        type="text"
        placeholder="Search agents..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full max-w-sm px-4 py-2 bg-bg-secondary border border-border rounded-lg text-sm text-text-primary placeholder:text-text-muted"
      />

      {isLoading ? (
        <div className="text-sm text-text-muted">Loading...</div>
      ) : filtered.length > 0 ? (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Name</th>
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Provider</th>
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Status</th>
                <th className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Computer Use</th>
                <th className="text-right py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((agent) => (
                <tr
                  key={agent.id}
                  className="border-b border-border/50 hover:bg-bg-tertiary/30 cursor-pointer transition-colors"
                  onClick={() => navigate(`/agents/${agent.id}`)}
                >
                  <td className="py-3 px-4">
                    <div className="text-text-primary font-medium">{agent.name}</div>
                    <div className="text-xs text-text-muted truncate max-w-xs">{agent.description}</div>
                  </td>
                  <td className="py-3 px-4 text-text-secondary capitalize">{agent.provider}</td>
                  <td className="py-3 px-4"><StatusBadge status={agent.status} /></td>
                  <td className="py-3 px-4 text-text-secondary">{agent.computer_use ? 'Yes' : 'No'}</td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}/edit`); }}
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={(e) => handleDelete(e, agent.id)}
                        disabled={deleteAgent.isPending}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <Card className="p-12 text-center">
          <p className="text-sm text-text-muted mb-4">
            {search ? 'No agents match your search.' : 'No agents yet. Create one to get started.'}
          </p>
          {!search && <Button onClick={() => navigate('/agents/new')}>Create your first agent</Button>}
        </Card>
      )}
    </div>
  );
}
