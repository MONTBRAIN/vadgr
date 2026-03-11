import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAgent, useDeleteAgent, useRunAgent } from '../hooks/useAgents';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';
import { PixelBack, PixelPlay, PixelGear, PixelStep, PixelTerminal } from '../components/ui/PixelIcon';
import type { SchemaField } from '../types';

export function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: agent, isLoading } = useAgent(id ?? '');
  const deleteAgent = useDeleteAgent();
  const runAgent = useRunAgent();
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [showRunForm, setShowRunForm] = useState(false);

  if (isLoading) return <div className="text-sm text-text-muted p-10">Loading...</div>;
  if (!agent) return <div className="text-sm text-text-muted p-10">Agent not found.</div>;

  const isReady = agent.status === 'ready';
  const isBusy = agent.status === 'creating' || agent.status === 'updating';

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
    <div>
      <div
        onClick={() => navigate('/agents')}
        className="inline-flex items-center gap-1.5 mb-5 cursor-pointer font-body text-xs text-text-muted hover:text-text-primary transition-colors"
      >
        <PixelBack size={12} color="var(--color-text-muted)" /> Back to Agents
      </div>

      <div className="flex items-start justify-between mb-7">
        <div>
          <h1 className="font-heading text-[28px] font-semibold text-text-primary tracking-tight mb-1.5">{agent.name}</h1>
          <p className="font-body text-[13px] text-text-muted font-light max-w-[600px] leading-relaxed">{agent.description || 'No description'}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => navigate(`/agents/${agent.id}/edit`)}>Edit</Button>
          <Button variant="danger" size="sm" onClick={handleDelete}>Delete</Button>
          <Button size="sm" onClick={() => setShowRunForm(!showRunForm)} disabled={!isReady}>
            <PixelPlay size={12} color="var(--color-bg-primary)" /> {isBusy ? 'Generating...' : 'Start Run'}
          </Button>
        </div>
      </div>

      {isBusy && (
        <Card className="p-4 border-info/30 bg-info/5 mb-6">
          <p className="text-sm text-info font-body">
            Agent is {agent.status}. Forge is generating the agent files. This may take a few minutes.
          </p>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-5 mb-6">
        {/* Configuration */}
        <Card className="px-7 py-6">
          <div className="flex items-center gap-2.5 mb-4">
            <PixelGear size={16} color="var(--color-text-muted)" hole="var(--color-bg-secondary)" />
            <h2 className="font-heading text-lg font-semibold text-text-primary">Configuration</h2>
          </div>
          <div className="grid grid-cols-2 gap-5">
            <ConfigItem label="Status"><StatusBadge status={agent.status} /></ConfigItem>
            <ConfigItem label="Type"><span className="font-body text-[10px] font-semibold uppercase tracking-wider text-accent">{agent.type}</span></ConfigItem>
            <ConfigItem label="Provider"><span className="font-mono text-[11px] bg-badge-bg px-2 py-0.5 rounded-md text-text-muted">{agent.provider}</span></ConfigItem>
            <ConfigItem label="Model"><span className="font-mono text-[11px] text-text-muted">{agent.model}</span></ConfigItem>
            <ConfigItem label="Computer Use"><span className={`font-body text-xs ${agent.computer_use ? 'text-success' : 'text-text-muted'}`}>{agent.computer_use ? 'Enabled' : 'Disabled'}</span></ConfigItem>
            <ConfigItem label="Created"><span className="font-body text-xs text-text-muted">{new Date(agent.created_at).toLocaleDateString()}</span></ConfigItem>
          </div>
        </Card>

        {/* Workflow Steps */}
        <Card className="px-7 py-6">
          <div className="flex items-center gap-2.5 mb-4">
            <PixelStep size={16} color="var(--color-info)" />
            <h2 className="font-heading text-lg font-semibold text-text-primary">Workflow Steps</h2>
          </div>
          <div className="flex flex-col gap-2">
            {agent.steps.length > 0 ? agent.steps.map((step, i) => {
              const stepObj = typeof step === 'string' ? { name: step, computer_use: false } : step;
              return (
                <div key={i} className="flex items-center justify-between gap-3 px-3.5 py-2.5 bg-hover-bg rounded-[10px] border border-border">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-heading text-[13px] font-bold text-accent w-5 shrink-0">{i + 1}</span>
                    <span className="font-mono text-xs text-text-primary truncate">{stepObj.name}</span>
                  </div>
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium shrink-0 ${
                    stepObj.computer_use
                      ? 'bg-accent/15 text-accent border border-accent/40'
                      : 'bg-bg-tertiary text-text-muted border border-border/50'
                  }`}>
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
                      <rect x="1" y="2" width="14" height="9" rx="1.5"/>
                      <line x1="5" y1="13.5" x2="11" y2="13.5"/>
                      <line x1="8" y1="11" x2="8" y2="13.5"/>
                      {stepObj.computer_use && <circle cx="8" cy="6.5" r="1.5" fill="currentColor" stroke="none"/>}
                    </svg>
                    {stepObj.computer_use ? 'Desktop' : 'CLI'}
                  </span>
                </div>
              );
            }) : (
              <p className="text-xs text-text-muted font-body">No steps defined.</p>
            )}
          </div>
        </Card>
      </div>

      {/* Input/Output Schema */}
      {(agent.input_schema.length > 0 || agent.output_schema.length > 0) && (
        <Card className="px-7 py-6 mb-6">
          <div className="flex items-center gap-2.5 mb-4">
            <PixelTerminal size={16} color="var(--color-text-muted)" />
            <h2 className="font-heading text-lg font-semibold text-text-primary">Input / Output Schema</h2>
          </div>
          <div className="grid grid-cols-2 gap-5">
            {agent.input_schema.length > 0 && (
              <SchemaDisplay label="Input Schema" fields={agent.input_schema} />
            )}
            {agent.output_schema.length > 0 && (
              <SchemaDisplay label="Output Schema" fields={agent.output_schema} />
            )}
          </div>
        </Card>
      )}

      {/* Run Form */}
      {showRunForm && isReady && (
        <Card className="px-7 py-6 mb-6">
          <h2 className="font-heading text-lg font-semibold text-text-primary mb-4">Run Agent</h2>
          {agent.input_schema.length > 0 ? (
            agent.input_schema.map((field) => (
              <div key={field.name} className="mb-3">
                <label className="block font-body text-sm text-text-secondary mb-1.5">
                  {field.name} {field.required && <span className="text-danger">*</span>}
                </label>
                <input
                  type={field.type === 'number' ? 'number' : 'text'}
                  value={inputs[field.name] ?? ''}
                  onChange={(e) => setInputs({ ...inputs, [field.name]: e.target.value })}
                  className="w-full px-3.5 py-2.5 bg-bg-input border border-border rounded-[10px] text-sm text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                  placeholder={`Enter ${field.name}`}
                />
              </div>
            ))
          ) : (
            <div className="mb-3">
              <label className="block font-body text-sm text-text-secondary mb-1.5">Task</label>
              <textarea
                value={inputs['task'] ?? ''}
                onChange={(e) => setInputs({ ...inputs, task: e.target.value })}
                className="w-full px-3.5 py-2.5 bg-bg-input border border-border rounded-[10px] text-sm text-text-primary placeholder:text-text-muted focus:border-accent transition-colors resize-y min-h-[80px]"
                placeholder="Describe what the agent should do"
                rows={3}
              />
            </div>
          )}
          <Button onClick={handleRun} disabled={runAgent.isPending}>
            {runAgent.isPending ? 'Starting...' : 'Start Run'}
          </Button>
        </Card>
      )}
    </div>
  );
}

function ConfigItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">{label}</p>
      {children}
    </div>
  );
}

function SchemaDisplay({ label, fields }: { label: string; fields: SchemaField[] }) {
  return (
    <div>
      <p className="font-body text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-2.5">{label}</p>
      <div className="space-y-1.5">
        {fields.map((f) => (
          <div key={f.name} className="flex items-center gap-3 text-sm">
            <span className="text-text-primary font-mono text-xs">{f.name}</span>
            <span className="text-text-muted text-[10px] font-body">({f.type})</span>
            {f.required && <span className="text-[10px] text-danger font-body">required</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
