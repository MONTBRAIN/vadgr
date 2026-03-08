import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { TextArea } from '../ui/TextArea';
import { Select } from '../ui/Select';
import { Toggle } from '../ui/Toggle';
import { SchemaEditor } from './SchemaEditor';
import { useCreateAgent, useUpdateAgent } from '../../hooks/useAgents';
import type { Agent, SchemaField } from '../../types';

const providerOptions = [
  { value: 'claude_code', label: 'Claude Code' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'openai', label: 'OpenAI' },
];

const modelOptions: Record<string, { value: string; label: string }[]> = {
  claude_code: [{ value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' }],
  anthropic: [
    { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
    { value: 'claude-opus-4-6', label: 'Claude Opus 4.6' },
  ],
  openai: [
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  ],
};

interface AgentFormProps {
  agent?: Agent;
}

export function AgentForm({ agent }: AgentFormProps) {
  const navigate = useNavigate();
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();

  const [name, setName] = useState(agent?.name ?? '');
  const [description, setDescription] = useState(agent?.description ?? '');
  const [provider, setProvider] = useState(agent?.provider ?? 'claude_code');
  const [model, setModel] = useState(agent?.model ?? 'claude-sonnet-4-6');
  const [computerUse, setComputerUse] = useState(agent?.computer_use ?? false);
  const [inputSchema, setInputSchema] = useState<SchemaField[]>(agent?.input_schema ?? []);
  const [outputSchema, setOutputSchema] = useState<SchemaField[]>(agent?.output_schema ?? []);

  const isEditing = !!agent;
  const isPending = createAgent.isPending || updateAgent.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isEditing) {
      await updateAgent.mutateAsync({
        id: agent.id,
        body: { name, description, provider, model, computer_use: computerUse, input_schema: inputSchema, output_schema: outputSchema },
      });
      navigate(`/agents/${agent.id}`);
    } else {
      const created = await createAgent.mutateAsync({ name, description, provider, model, computer_use: computerUse });
      if (inputSchema.length > 0 || outputSchema.length > 0) {
        await updateAgent.mutateAsync({ id: created.id, body: { input_schema: inputSchema, output_schema: outputSchema } });
      }
      navigate('/agents');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      <Input
        label="Agent Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="e.g. Research Agent"
        required
        maxLength={200}
      />

      <TextArea
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Describe what this agent should do in plain language."
        rows={4}
        maxLength={10000}
      />

      <div className="grid grid-cols-2 gap-6">
        <Select
          label="Provider"
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value);
            const models = modelOptions[e.target.value];
            if (models?.length) setModel(models[0].value);
          }}
          options={providerOptions}
        />
        <div className="flex items-end">
          <Toggle label="Computer Use" checked={computerUse} onChange={setComputerUse} />
        </div>
      </div>

      <Select
        label="Model"
        value={model}
        onChange={(e) => setModel(e.target.value)}
        options={modelOptions[provider] ?? []}
      />

      <SchemaEditor label="Input Schema" fields={inputSchema} onChange={setInputSchema} />
      <SchemaEditor label="Output Schema" fields={outputSchema} onChange={setOutputSchema} />

      <div className="flex items-center gap-3 pt-4">
        <Button type="submit" disabled={!name.trim() || isPending}>
          {isPending ? 'Saving...' : isEditing ? 'Save Changes' : 'Create Agent'}
        </Button>
        <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
