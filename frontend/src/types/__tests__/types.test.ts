import { describe, it, expect } from 'vitest';
import type { Agent, Run, SchemaField } from '../index';

describe('Type definitions', () => {
  it('Agent type has required fields', () => {
    const agent: Agent = {
      id: '1',
      name: 'Test',
      description: 'desc',
      type: 'agent',
      status: 'creating',
      forge_path: '',
      samples: [],
      input_schema: [],
      output_schema: [],
      computer_use: false,
      forge_config: {},
      provider: 'anthropic',
      model: 'claude-sonnet-4-6',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };
    expect(agent.id).toBe('1');
    expect(agent.type).toBe('agent');
  });

  it('Run type has required fields', () => {
    const run: Run = {
      id: '1',
      project_id: null,
      agent_id: '2',
      status: 'queued',
      inputs: { topic: 'test' },
      outputs: {},
      started_at: null,
      completed_at: null,
    };
    expect(run.status).toBe('queued');
    expect(run.agent_id).toBe('2');
  });

  it('SchemaField type has required fields', () => {
    const field: SchemaField = {
      name: 'topic',
      type: 'text',
      required: true,
    };
    expect(field.name).toBe('topic');
    expect(field.required).toBe(true);
  });
});
