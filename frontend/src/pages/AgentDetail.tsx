import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAgent, useDeleteAgent, useRunAgent } from '../hooks/useAgents';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';
import type { SchemaField } from '../types';

export function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: agent, isLoading } = useAgent(id ?? '');
  const deleteAgent = useDeleteAgent();
  const runAgent = useRunAgent();
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [showRunForm, setShowRunForm] = useState(false);

  if (isLoading) return <div className="text-sm text-text-muted">Loading...</div>;
  if (!agent) return <div className="text-sm text-text-muted">Agent not found.</div>;

  const handleRun = async () => {
    const result = await runAgent.mutateAsync({ id: agent.id, inputs });
    navigate(`/runs/${result.run_id}`);
  };

  const handleDelete = async () => {
    if (confirm('Delete this agent?')) {
      await deleteAgent.mutateAsync(agent.id);
      navigate('/agents');
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-text-primary">{agent.name}</h1>
          <StatusBadge status={agent.status} />
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => navigate(`/agents/${agent.id}/edit`)}>Edit</Button>
          <Button variant="danger" onClick={handleDelete}>Delete</Button>
          <Button onClick={() => setShowRunForm(!showRunForm)}>Run</Button>
        </div>
      </div>

      <Card className="p-5 space-y-4">
        <div>
          <label className="text-xs text-text-muted uppercase tracking-wider">Description</label>
          <p className="text-sm text-text-secondary mt-1">{agent.description || 'No description'}</p>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wider">Provider</label>
            <p className="text-sm text-text-primary mt-1 capitalize">{agent.provider}</p>
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wider">Model</label>
            <p className="text-sm text-text-primary mt-1">{agent.model}</p>
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wider">Computer Use</label>
            <p className="text-sm text-text-primary mt-1">{agent.computer_use ? 'Enabled' : 'Disabled'}</p>
          </div>
        </div>
        {agent.input_schema.length > 0 && (
          <SchemaDisplay label="Input Schema" fields={agent.input_schema} />
        )}
        {agent.output_schema.length > 0 && (
          <SchemaDisplay label="Output Schema" fields={agent.output_schema} />
        )}
      </Card>

      {showRunForm && (
        <Card className="p-5 space-y-4">
          <h2 className="text-sm font-medium text-text-primary">Run Agent</h2>
          {agent.input_schema.length > 0 ? (
            agent.input_schema.map((field) => (
              <div key={field.name} className="space-y-1.5">
                <label className="block text-sm text-text-secondary">
                  {field.name} {field.required && <span className="text-danger">*</span>}
                </label>
                <input
                  type={field.type === 'number' ? 'number' : 'text'}
                  value={inputs[field.name] ?? ''}
                  onChange={(e) => setInputs({ ...inputs, [field.name]: e.target.value })}
                  className="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-sm text-text-primary"
                  placeholder={`Enter ${field.name}`}
                />
              </div>
            ))
          ) : (
            <p className="text-xs text-text-muted">No inputs required. Click run to start.</p>
          )}
          <Button onClick={handleRun} disabled={runAgent.isPending}>
            {runAgent.isPending ? 'Starting...' : 'Start Run'}
          </Button>
        </Card>
      )}
    </div>
  );
}

function SchemaDisplay({ label, fields }: { label: string; fields: SchemaField[] }) {
  return (
    <div>
      <label className="text-xs text-text-muted uppercase tracking-wider">{label}</label>
      <div className="mt-2 space-y-1">
        {fields.map((f) => (
          <div key={f.name} className="flex items-center gap-3 text-sm">
            <span className="text-text-primary font-mono">{f.name}</span>
            <span className="text-text-muted text-xs">({f.type})</span>
            {f.required && <span className="text-xs text-danger">required</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
