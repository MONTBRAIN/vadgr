import { useState, useRef, useEffect } from 'react';
import type { ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { TextArea } from '../ui/TextArea';
import { Select } from '../ui/Select';
import { SchemaEditor } from './SchemaEditor';
import { useCreateAgent, useUpdateAgent, useImportAgentPackage } from '../../hooks/useAgents';
import { useProviders } from '../../hooks/useProviders';
import { api } from '../../api/client';
import { BUSY_STATUSES } from '../../types';
import type { Agent, SchemaField } from '../../types';

interface AgentFormProps {
  agent?: Agent;
}

export function AgentForm({ agent }: AgentFormProps) {
  const navigate = useNavigate();
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const { data: providers } = useProviders();

  const providerOptions = (providers ?? []).map((p) => ({ value: p.id, label: p.name }));
  const modelOptions: Record<string, { value: string; label: string }[]> = {};
  for (const p of providers ?? []) {
    modelOptions[p.id] = p.models.map((m) => ({ value: m.id, label: m.name }));
  }

  const [name, setName] = useState(agent?.name ?? '');
  const [description, setDescription] = useState(agent?.description ?? '');
  const [steps, setSteps] = useState<{ name: string; computer_use: boolean }[]>(
    (agent?.steps ?? []).map((s: string | { name: string; computer_use: boolean }) =>
      typeof s === 'string' ? { name: s, computer_use: false } : s
    )
  );
  const [stepInput, setStepInput] = useState('');
  const [provider, setProvider] = useState(agent?.provider ?? 'claude_code');
  const [model, setModel] = useState(agent?.model ?? 'claude-sonnet-4-6');
  const [inputSchema, setInputSchema] = useState<SchemaField[]>(agent?.input_schema ?? []);
  const [outputSchema, setOutputSchema] = useState<SchemaField[]>(agent?.output_schema ?? []);

  // Step editing
  const [editingStep, setEditingStep] = useState<number | null>(null);
  const [editingStepValue, setEditingStepValue] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  // Step drag-and-drop
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const dragNode = useRef<HTMLDivElement | null>(null);

  // Import agent
  const importAgent = useImportAgentPackage();
  const importFileRef = useRef<HTMLInputElement>(null);
  const handleImportChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const imported = await importAgent.mutateAsync(file);
      navigate(`/agents/${imported.id}`);
    } finally {
      event.target.value = '';
    }
  };

  // Check if computer use is enabled globally
  const [cuEnabled, setCuEnabled] = useState(true);
  useEffect(() => {
    api.get<{ enabled: boolean }>('/settings/computer-use')
      .then((data) => setCuEnabled(data.enabled))
      .catch(() => {});
  }, []);

  const isEditing = !!agent;
  const isBusy = agent?.status !== undefined && BUSY_STATUSES.has(agent.status);
  const isPending = createAgent.isPending || updateAgent.isPending;

  const addStep = () => {
    const trimmed = stepInput.trim();
    if (trimmed && !steps.some(s => s.name === trimmed)) {
      setSteps([...steps, { name: trimmed, computer_use: false }]);
      setStepInput('');
    }
  };

  const removeStep = (index: number) => {
    setSteps(steps.filter((_, i) => i !== index));
    if (editingStep === index) setEditingStep(null);
  };

  const toggleStepComputerUse = (index: number) => {
    setSteps(steps.map((s, i) => i === index ? { ...s, computer_use: !s.computer_use } : s));
  };

  const startEditingStep = (index: number) => {
    setEditingStep(index);
    setEditingStepValue(steps[index].name);
    requestAnimationFrame(() => editInputRef.current?.focus());
  };

  const commitStepEdit = () => {
    if (editingStep === null) return;
    const trimmed = editingStepValue.trim();
    if (trimmed && trimmed !== steps[editingStep].name) {
      setSteps(steps.map((s, i) => i === editingStep ? { ...s, name: trimmed } : s));
    }
    setEditingStep(null);
  };

  const handleStepEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { e.preventDefault(); commitStepEdit(); }
    if (e.key === 'Escape') setEditingStep(null);
  };

  const handleStepKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addStep();
    }
  };

  // Step drag handlers
  const handleStepDragStart = (e: React.DragEvent, index: number) => {
    setDragIndex(index);
    dragNode.current = e.currentTarget as HTMLDivElement;
    e.dataTransfer.effectAllowed = 'move';
    requestAnimationFrame(() => {
      if (dragNode.current) dragNode.current.style.opacity = '0.4';
    });
  };

  const handleStepDragEnd = () => {
    if (dragNode.current) dragNode.current.style.opacity = '1';
    if (dragIndex !== null && dropTarget !== null && dragIndex !== dropTarget) {
      const reordered = [...steps];
      const [moved] = reordered.splice(dragIndex, 1);
      reordered.splice(dropTarget, 0, moved);
      setSteps(reordered);
    }
    setDragIndex(null);
    setDropTarget(null);
    dragNode.current = null;
  };

  const handleStepDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDropTarget(index);
  };

  const hasComputerUse = steps.some(s => s.computer_use);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isBusy) return;
    if (isEditing) {
      await updateAgent.mutateAsync({
        id: agent.id,
        body: {
          name, description, steps, provider, model,
          computer_use: hasComputerUse,
          input_schema: inputSchema,
          output_schema: outputSchema,
        },
      });
      navigate(`/agents/${agent.id}`);
    } else {
      await createAgent.mutateAsync({
        name, description, steps, provider, model,
        computer_use: hasComputerUse,
      });
      navigate('/agents');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      <Input
        label="Agent Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="e.g. research-agent"
        required
        maxLength={200}
        disabled={isBusy}
      />

      <TextArea
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Describe what this agent should do in plain language."
        rows={4}
        maxLength={10000}
        required
        disabled={isBusy}
      />

      {/* Steps Editor */}
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-text-secondary">Steps</label>
          <p className="text-xs text-text-muted mt-1">
            Optional but recommended. Breaking work into steps helps the agent produce better results. Drag to reorder, click to edit.
          </p>
        </div>
        {steps.length > 0 && (
          <div className="space-y-1.5">
            {steps.map((step, i) => (
              <div
                key={i}
                draggable={!isBusy}
                onDragStart={(e) => handleStepDragStart(e, i)}
                onDragEnd={handleStepDragEnd}
                onDragOver={(e) => handleStepDragOver(e, i)}
                className={`group flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg bg-bg-secondary border transition-colors ${
                  dropTarget === i && dragIndex !== i
                    ? 'border-accent/60'
                    : 'border-border'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  {/* Drag handle */}
                  {!isBusy && (
                    <div className="cursor-grab active:cursor-grabbing text-text-muted hover:text-text-secondary shrink-0" title="Drag to reorder">
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                        <circle cx="5.5" cy="3.5" r="1.2"/><circle cx="10.5" cy="3.5" r="1.2"/>
                        <circle cx="5.5" cy="8" r="1.2"/><circle cx="10.5" cy="8" r="1.2"/>
                        <circle cx="5.5" cy="12.5" r="1.2"/><circle cx="10.5" cy="12.5" r="1.2"/>
                      </svg>
                    </div>
                  )}
                  <span className="text-xs font-mono text-text-muted w-5 shrink-0">{i + 1}.</span>
                  {editingStep === i ? (
                    <input
                      ref={editInputRef}
                      value={editingStepValue}
                      onChange={(e) => setEditingStepValue(e.target.value)}
                      onBlur={commitStepEdit}
                      onKeyDown={handleStepEditKeyDown}
                      className="flex-1 min-w-0 px-2 py-0.5 bg-bg-input border border-accent rounded-md text-sm text-text-primary focus:outline-none"
                    />
                  ) : (
                    <span
                      className="text-sm text-text-primary truncate cursor-pointer hover:text-accent transition-colors"
                      onClick={() => !isBusy && startEditingStep(i)}
                      title="Click to edit"
                    >
                      {step.name}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => cuEnabled && toggleStepComputerUse(i)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                      step.computer_use
                        ? 'bg-accent/15 text-accent border border-accent/40 shadow-sm shadow-accent/10'
                        : 'bg-bg-tertiary text-text-muted border border-border/50 hover:border-border hover:text-text-secondary cursor-pointer'
                    } ${!cuEnabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    disabled={isBusy || !cuEnabled}
                    title={!cuEnabled ? 'Enable computer use in Settings to use desktop steps' : step.computer_use ? 'This step can take control of your computer: open apps, click, type, and navigate' : 'Click to let this step take control of your computer'}
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
                      <rect x="1" y="2" width="14" height="9" rx="1.5"/>
                      <line x1="5" y1="13.5" x2="11" y2="13.5"/>
                      <line x1="8" y1="11" x2="8" y2="13.5"/>
                      {step.computer_use && <circle cx="8" cy="6.5" r="1.5" fill="currentColor" stroke="none"/>}
                    </svg>
                    {step.computer_use ? 'Desktop' : 'CLI'}
                  </button>
                  <button
                    type="button"
                    onClick={() => removeStep(i)}
                    className="text-text-muted hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                    disabled={isBusy}
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/>
                    </svg>
                  </button>
                </div>
              </div>
            ))}
            <p className="text-[11px] text-text-muted pt-1">
              Click <span className="font-medium text-text-secondary">CLI</span> / <span className="font-medium text-text-secondary">Desktop</span> on each step to choose how it runs.
              CLI uses the terminal. Desktop lets the agent take control of your computer.
            </p>
          </div>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={stepInput}
            onChange={(e) => setStepInput(e.target.value)}
            onKeyDown={handleStepKeyDown}
            placeholder="Add a step and press Enter"
            className="flex-1 px-3 py-2 bg-bg-input border border-border rounded-lg text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
            disabled={isBusy}
          />
          <Button type="button" variant="secondary" size="sm" onClick={addStep} disabled={!stepInput.trim() || isBusy}>
            + Add
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        <label className="block text-sm font-medium text-text-secondary">{isEditing ? 'Edit with' : 'Create with'}</label>
        <div className="grid grid-cols-2 gap-6">
        <Select
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value);
            const models = modelOptions[e.target.value];
            if (models?.length) setModel(models[0].value);
          }}
          options={providerOptions}
          disabled={isBusy}
        />
        <Select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          options={modelOptions[provider] ?? []}
          disabled={isBusy}
        />
        </div>
      </div>

      {hasComputerUse && (
        <div className="text-xs text-accent bg-accent/10 px-3 py-2 rounded-lg">
          Computer use enabled -- {steps.filter(s => s.computer_use).length} of {steps.length} steps use it
        </div>
      )}

      {isEditing && (
        <>
          <SchemaEditor label="Inputs" fields={inputSchema} onChange={setInputSchema} isInput={true} readOnly={isBusy} />
          <SchemaEditor label="Outputs" fields={outputSchema} onChange={setOutputSchema} isInput={false} readOnly={isBusy} />
        </>
      )}

      <div className="flex items-center gap-3 pt-4">
        <Button type="submit" disabled={!name.trim() || !description.trim() || isPending || isBusy}>
          {isPending ? 'Saving...' : isEditing ? 'Save Changes' : 'Create Agent'}
        </Button>
        <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
          Cancel
        </Button>
      </div>

      {!isEditing && (
        <div className="flex items-center gap-3 pt-2">
          <div className="flex-1 border-t border-border" />
          <span className="text-xs text-text-muted">or</span>
          <div className="flex-1 border-t border-border" />
        </div>
      )}

      {!isEditing && (
        <>
          <input
            ref={importFileRef}
            type="file"
            accept=".agnt,.zip"
            className="hidden"
            onChange={handleImportChange}
          />
          <button
            type="button"
            onClick={() => importFileRef.current?.click()}
            disabled={importAgent.isPending}
            className="w-full py-3 border border-dashed border-border rounded-lg text-sm text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors cursor-pointer"
          >
            {importAgent.isPending ? 'Importing...' : 'Import an existing agent (.agnt)'}
          </button>
        </>
      )}
    </form>
  );
}
