import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAgent, useDeleteAgent, useExportAgentPackage, useRunAgent, useUploadAgentArtifact } from '../hooks/useAgents';
import { useProviders } from '../hooks/useProviders';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge, ProviderBadge } from '../components/ui/Badge';
import { PixelBack, PixelGear, PixelPlay, PixelStep } from '../components/ui/PixelIcon';
import { BUSY_STATUSES } from '../types';
import type { ArtifactDescriptor, SchemaField } from '../types';

function renderInputField(
  field: SchemaField,
  value: string,
  onChange: (v: string) => void,
  error?: string,
) {
  const hasError = !!error;
  const base = `w-full px-3.5 py-2.5 bg-bg-input border rounded-[10px] text-sm text-text-primary placeholder:text-text-muted focus:border-accent transition-colors ${hasError ? 'border-danger' : 'border-border'}`;
  const label = field.label || field.name;

  return (
    <div key={field.name}>
      <label className="block font-body text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
        {label} {field.required && <span className="text-danger">*</span>}
      </label>
      {field.type === 'textarea' ? (
        <textarea
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          className={`${base} resize-none`}
        />
      ) : field.type === 'select' && field.options?.length ? (
        <select
          value={value || field.options[0]}
          onChange={(e) => onChange(e.target.value)}
          className={base}
        >
          {field.options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      ) : (
        <input
          type={field.type === 'url' ? 'url' : field.type === 'number' ? 'number' : 'text'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          className={`${base} ${field.type === 'url' ? 'font-mono text-xs' : ''}`}
        />
      )}
      {hasError ? (
        <p className="font-body text-[10px] text-danger mt-1">{error}</p>
      ) : field.description ? (
        <p className="font-body text-[10px] text-text-muted mt-1">{field.description}</p>
      ) : null}
    </div>
  );
}

function isArtifactField(field: SchemaField) {
  return field.type === 'file' || field.type === 'archive' || field.type === 'directory';
}

function renderStep(step: string | { name: string; computer_use: boolean }, index: number) {
  const stepObj = typeof step === 'string' ? { name: step, computer_use: false } : step;

  return (
    <div
      key={index}
      className="flex items-center justify-between gap-3 px-3.5 py-2.5 bg-hover-bg rounded-[10px] border border-border"
    >
      <div className="flex items-center gap-3 min-w-0">
        <span className="font-heading text-[13px] font-bold text-accent w-5 shrink-0">{index + 1}</span>
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
}

export function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: agent, isLoading } = useAgent(id ?? '');
  const { data: providers } = useProviders();
  const deleteAgent = useDeleteAgent();
  const exportAgentPackage = useExportAgentPackage();
  const runAgent = useRunAgent();
  const uploadArtifact = useUploadAgentArtifact();
  const [inputs, setInputs] = useState<Record<string, string | ArtifactDescriptor>>({});
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [runProvider, setRunProvider] = useState('');
  const [runModel, setRunModel] = useState('');

  const displayInputs: SchemaField[] = agent?.input_schema.length
    ? agent.input_schema
    : [{
        name: 'instructions',
        type: 'textarea',
        required: false,
        label: 'Instructions',
        placeholder: 'Describe what you want the agent to do',
      }];

  useEffect(() => {
    if (!agent) return;
    const defaults: Record<string, string> = {};
    for (const field of displayInputs) {
      if (field.type === 'select' && field.options?.length && !inputs[field.name]) {
        defaults[field.name] = field.options[0];
      }
    }
    if (Object.keys(defaults).length > 0) {
      setInputs((prev) => ({ ...defaults, ...prev }));
    }
  }, [agent?.id, displayInputs]);

  useEffect(() => {
    if (!agent) return;
    setRunProvider(agent.provider);
    setRunModel(agent.model);
  }, [agent?.id, agent?.provider, agent?.model]);

  useEffect(() => {
    if (!providers?.length || !runProvider) return;
    const selectedProvider = providers.find((provider) => provider.id === runProvider);
    if (!selectedProvider?.models.length) return;
    const hasCurrentModel = selectedProvider.models.some((model) => model.id === runModel);
    if (!hasCurrentModel) {
      setRunModel(selectedProvider.models[0].id);
    }
  }, [providers, runProvider, runModel]);

  if (isLoading) return <div className="text-sm text-text-muted p-10">Loading...</div>;
  if (!agent) return <div className="text-sm text-text-muted p-10">Agent not found.</div>;

  const isReady = agent.status === 'ready';
  const isBusy = BUSY_STATUSES.has(agent.status);
  const providerOptions = providers ?? [];
  const modelOptions = providerOptions.find((provider) => provider.id === runProvider)?.models ?? [];

  const handleRun = async () => {
    const errors: Record<string, string> = {};
    for (const field of displayInputs) {
      const value = inputs[field.name];
      const isMissing = typeof value === 'string' ? !value.trim() : !value;
      if (field.required && isMissing) {
        errors[field.name] = `${field.label || field.name} is required`;
      }
    }
    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors);
      return;
    }

    setValidationErrors({});
    const runtimeOverride = runProvider !== agent.provider || runModel !== agent.model;
    const result = await runAgent.mutateAsync({
      id: agent.id,
      inputs,
      provider: runtimeOverride ? runProvider : undefined,
      model: runtimeOverride ? runModel : undefined,
    });
    navigate(`/runs/${result.run_id}`);
  };

  const handleDelete = async () => {
    if (confirm('Delete this agent?')) {
      await deleteAgent.mutateAsync(agent.id);
      navigate('/agents');
    }
  };

  const handleExport = async () => {
    const blob = await exportAgentPackage.mutateAsync(agent.id);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const safeName = (agent.name || agent.id).trim().replace(/\s+/g, '-').toLowerCase();
    link.href = url;
    link.download = `${safeName || agent.id}.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
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
          <Button variant="secondary" size="sm" onClick={handleExport} disabled={exportAgentPackage.isPending}>
            Export
          </Button>
          <Button variant="secondary" size="sm" onClick={() => navigate(`/agents/${agent.id}/edit`)} disabled={isBusy}>Edit</Button>
          <Button variant="danger" size="sm" onClick={handleDelete}>Delete</Button>
          <Button size="sm" onClick={handleRun} disabled={runAgent.isPending || uploadArtifact.isPending || !isReady}>
            <PixelPlay size={12} color="var(--color-bg-primary)" /> {isBusy ? 'Generating...' : uploadArtifact.isPending ? 'Uploading...' : 'Start Run'}
          </Button>
        </div>
      </div>

      {isBusy && (
        <Card className="p-4 border-info/30 bg-info/5 mb-6">
          <p className="text-sm text-info font-body">
            Agent is {agent.status}. The agent files are being prepared. This may take a few minutes.
          </p>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-5 mb-6">
        <Card className="px-7 py-6">
          <div className="flex items-center gap-2.5 mb-4">
            <PixelGear size={16} color="var(--color-text-muted)" hole="var(--color-bg-secondary)" />
            <h2 className="font-heading text-lg font-semibold text-text-primary">Configuration</h2>
          </div>
          <div className="grid grid-cols-2 gap-5">
            <ConfigItem label="Status"><StatusBadge status={agent.status} /></ConfigItem>
            <ConfigItem label="Type"><span className="font-body text-[10px] font-semibold uppercase tracking-wider text-accent">{agent.type}</span></ConfigItem>
            <ConfigItem label="Created With"><ProviderBadge provider={agent.provider} label="" /></ConfigItem>
            <ConfigItem label="Creation Model"><span className="font-mono text-[11px] text-text-muted">{agent.model}</span></ConfigItem>
            <ConfigItem label="Computer Use"><span className={`font-body text-xs ${agent.computer_use ? 'text-success' : 'text-text-muted'}`}>{agent.computer_use ? 'Enabled' : 'Disabled'}</span></ConfigItem>
            <ConfigItem label="Created"><span className="font-body text-xs text-text-muted">{new Date(agent.created_at).toLocaleDateString()}</span></ConfigItem>
          </div>
        </Card>

        <Card className="px-7 py-6">
          <div className="flex items-center gap-2.5 mb-4">
            <PixelStep size={16} color="var(--color-info)" />
            <h2 className="font-heading text-lg font-semibold text-text-primary">Workflow Steps</h2>
          </div>
          <div className="flex flex-col gap-2">
            {agent.steps.length > 0 ? agent.steps.map(renderStep) : (
              <p className="text-xs text-text-muted font-body">No steps defined.</p>
            )}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-5 mb-6">
        <Card className="px-7 py-6">
          <div className="flex items-center gap-2.5 mb-4">
            <PixelGear size={16} color="var(--color-text-muted)" hole="var(--color-bg-secondary)" />
            <h2 className="font-heading text-lg font-semibold text-text-primary">Run Configuration</h2>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="run-provider" className="block font-body text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
                Run Provider
              </label>
              <select
                id="run-provider"
                value={runProvider}
                onChange={(e) => {
                  const nextProvider = e.target.value;
                  setRunProvider(nextProvider);
                  const nextModels = providerOptions.find((provider) => provider.id === nextProvider)?.models ?? [];
                  setRunModel(nextModels[0]?.id ?? '');
                }}
                className="w-full px-3.5 py-2.5 bg-bg-input border border-border rounded-[10px] text-sm text-text-primary"
              >
                {providerOptions.map((provider) => (
                  <option key={provider.id} value={provider.id}>{provider.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="run-model" className="block font-body text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
                Run Model
              </label>
              <select
                id="run-model"
                value={runModel}
                onChange={(e) => setRunModel(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-bg-input border border-border rounded-[10px] text-sm text-text-primary"
              >
                {modelOptions.map((model) => (
                  <option key={model.id} value={model.id}>{model.name}</option>
                ))}
              </select>
            </div>
          </div>
        </Card>

        <Card className="px-7 py-6">
          <div className="flex items-center gap-2.5 mb-4">
            <PixelStep size={16} color="var(--color-info)" />
            <h2 className="font-heading text-lg font-semibold text-text-primary">Run Notes</h2>
          </div>
          <p className="font-body text-sm text-text-muted leading-relaxed">
            If you do not change these fields, the run will use the same provider and model that created the agent.
          </p>
        </Card>
      </div>

      <div className="grid gap-5 mb-6 items-stretch grid-cols-2">
        <Card className="px-7 py-6 flex flex-col">
          <div className="flex items-center gap-2.5 mb-4">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="1" y="3" width="14" height="10" rx="1.5" stroke="var(--color-success)" strokeWidth="1.3"/>
              <path d="M4 7.5h5M4 9.5h3" stroke="var(--color-success)" strokeWidth="1" strokeLinecap="round"/>
              <path d="M11 6l2 2.5-2 2.5" stroke="var(--color-success)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <h2 className="font-heading text-lg font-semibold text-text-primary">Inputs</h2>
          </div>
          <div className="flex flex-col gap-3 flex-1">
            {displayInputs.map((field) => {
              const fieldValue = inputs[field.name];

              if (isArtifactField(field)) {
                const artifact = fieldValue;
                const hasError = !!validationErrors[field.name];
                return (
                  <div key={field.name}>
                    <label className="block font-body text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
                      {field.label || field.name} {field.required && <span className="text-danger">*</span>}
                    </label>
                    <div className={`w-full px-3.5 py-2.5 bg-bg-input border rounded-[10px] ${hasError ? 'border-danger' : 'border-border'}`}>
                      {artifact && typeof artifact !== 'string' ? (
                        <div className="inline-flex items-center gap-2 px-2.5 py-1.5 bg-info/20 border border-info/40 rounded-lg">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-info shrink-0">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                            <polyline points="14 2 14 8 20 8" />
                          </svg>
                          <span className="font-mono text-xs text-info truncate">
                            {artifact.filename}
                          </span>
                          <button
                            type="button"
                            onClick={() => setInputs((prev) => ({ ...prev, [field.name]: undefined }))}
                            className="text-info/70 hover:text-info transition-colors text-sm font-bold"
                            aria-label={`Remove ${field.label || field.name}`}
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <label className="flex items-center gap-2 cursor-pointer">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-info shrink-0">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                            <polyline points="17 8 12 3 7 8" />
                            <line x1="12" y1="3" x2="12" y2="15" />
                          </svg>
                          <span className="text-sm text-text-primary">Choose file</span>
                          <span className="text-sm text-text-muted">No file chosen</span>
                          <input
                            type="file"
                            aria-label={field.label || field.name}
                            accept={field.accept?.join(',')}
                            disabled={uploadArtifact.isPending}
                            onChange={async (e) => {
                              const selected = e.target.files?.[0];
                              if (!selected || !id) return;
                              try {
                                const descriptor = await uploadArtifact.mutateAsync({
                                  id,
                                  fieldName: field.name,
                                  file: selected,
                                });
                                setInputs((prev) => ({ ...prev, [field.name]: descriptor }));
                                if (validationErrors[field.name]) {
                                  setValidationErrors((prev) => {
                                    const next = { ...prev };
                                    delete next[field.name];
                                    return next;
                                  });
                                }
                              } catch (error) {
                                setValidationErrors((prev) => ({
                                  ...prev,
                                  [field.name]: error instanceof Error ? error.message : 'Upload failed',
                                }));
                              }
                            }}
                            className="hidden"
                          />
                        </label>
                      )}
                    </div>
                    {hasError ? (
                      <p className="font-body text-[10px] text-danger mt-1">{validationErrors[field.name]}</p>
                    ) : field.description ? (
                      <p className="font-body text-[10px] text-text-muted mt-1">{field.description}</p>
                    ) : null}
                  </div>
                );
              }

              return renderInputField(
                field,
                typeof fieldValue === 'string' ? fieldValue : '',
                (value) => {
                  setInputs((prev) => ({ ...prev, [field.name]: value }));
                  if (validationErrors[field.name]) {
                    setValidationErrors((prev) => {
                      const next = { ...prev };
                      delete next[field.name];
                      return next;
                    });
                  }
                },
                validationErrors[field.name],
              );
            })}
            <div className="mt-auto pt-5 border-t border-border">
              <Button onClick={handleRun} disabled={runAgent.isPending || !isReady}>
                <PixelPlay size={12} color="var(--color-bg-primary)" />
                {runAgent.isPending ? 'Starting...' : 'Start Run'}
              </Button>
            </div>
          </div>
        </Card>

        <Card className="px-7 py-6 flex flex-col">
          <div className="flex items-center gap-2.5 mb-4">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="1" y="3" width="14" height="10" rx="1.5" stroke="var(--color-accent)" strokeWidth="1.3"/>
              <path d="M5 6l-2 2.5L5 11" stroke="var(--color-accent)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M8 7.5h5M10 9.5h3" stroke="var(--color-accent)" strokeWidth="1" strokeLinecap="round"/>
            </svg>
            <h2 className="font-heading text-lg font-semibold text-text-primary">Outputs</h2>
          </div>
          {agent.output_schema.length > 0 ? (
            <div className="flex flex-col gap-2.5 flex-1">
              {agent.output_schema.map((field, i) => (
                <div key={field.name} className="flex items-start gap-3 px-3.5 py-3 bg-hover-bg rounded-[10px] border border-border">
                  <span className={`mt-0.5 shrink-0 ${i % 3 === 0 ? 'text-accent' : i % 3 === 1 ? 'text-success' : 'text-info'}`}>
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2">
                      <path d="M4 1.5h5.5L13 5v9.5a1 1 0 01-1 1H4a1 1 0 01-1-1v-13a1 1 0 011-1z"/>
                      <path d="M9 1.5V5.5h4"/>
                      <path d="M5.5 8h5M5.5 10h5M5.5 12h3" strokeLinecap="round"/>
                    </svg>
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-body text-sm text-text-primary font-medium">{field.label || field.name}</span>
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">{field.type}</span>
                    </div>
                    {field.description && (
                      <p className="font-body text-[11px] text-text-muted leading-relaxed">{field.description}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex-1 rounded-[10px] border border-dashed border-border px-4 py-5 text-sm text-text-muted font-body">
              Outputs will be inferred by Forge after the agent runs.
            </div>
          )}
        </Card>
      </div>
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
