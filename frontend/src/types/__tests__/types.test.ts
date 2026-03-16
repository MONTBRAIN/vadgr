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
      steps: [],
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
      provider: 'codex',
      model: 'gpt-5-codex',
      log_path: null,
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

  it('SchemaField accepts all optional rich fields', () => {
    const field: SchemaField = {
      name: 'depth',
      type: 'select',
      required: false,
      label: 'Analysis Depth',
      description: 'How thorough the research should be',
      placeholder: 'e.g. standard',
      options: ['quick', 'standard', 'deep'],
    };
    expect(field.label).toBe('Analysis Depth');
    expect(field.description).toBe('How thorough the research should be');
    expect(field.options).toEqual(['quick', 'standard', 'deep']);
  });

  it('SchemaField supports all valid input types', () => {
    const types: SchemaField['type'][] = ['text', 'url', 'textarea', 'select', 'number', 'boolean', 'file', 'markdown'];
    for (const type of types) {
      const field: SchemaField = { name: 'f', type, required: false };
      expect(field.type).toBe(type);
    }
  });

  it('SchemaField optional fields default to undefined', () => {
    const field: SchemaField = { name: 'topic', type: 'text', required: true };
    expect(field.label).toBeUndefined();
    expect(field.description).toBeUndefined();
    expect(field.placeholder).toBeUndefined();
    expect(field.options).toBeUndefined();
  });
});
