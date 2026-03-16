import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import type { SchemaField } from '../../types';

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: 'agent-1' }),
  useNavigate: () => mockNavigate,
}));

// Mock hooks — agent with empty schemas by default
const mockRunAgent = { mutateAsync: vi.fn(), isPending: false };

const baseAgent = {
  id: 'agent-1',
  name: 'Test Agent',
  description: 'A test agent',
  status: 'ready',
  type: 'agent',
  provider: 'anthropic',
  model: 'claude-sonnet-4-6',
  computer_use: false,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  forge_path: '',
  forge_config: {},
  samples: [],
  steps: [
    { name: 'Analyze code', computer_use: false },
    { name: 'Write tests', computer_use: false },
    { name: 'Create PR', computer_use: true },
  ],
  input_schema: [] as SchemaField[],
  output_schema: [] as SchemaField[],
};

let mockAgent = { ...baseAgent };

vi.mock('../../hooks/useAgents', () => ({
  useAgent: () => ({ data: mockAgent, isLoading: false }),
  useDeleteAgent: () => ({ mutateAsync: vi.fn() }),
  useRunAgent: () => mockRunAgent,
}));

vi.mock('../../hooks/useProviders', () => ({
  useProviders: () => ({
    data: [
      {
        id: 'claude_code',
        name: 'Claude Code',
        models: [
          { id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6' },
          { id: 'claude-opus-4-6', name: 'Claude Opus 4.6' },
        ],
      },
      {
        id: 'codex',
        name: 'OpenAI Codex CLI',
        models: [
          { id: 'gpt-5-codex', name: 'GPT-5 Codex' },
          { id: 'gpt-5-mini', name: 'GPT-5 Mini' },
        ],
      },
    ],
  }),
}));

import { AgentDetail } from '../AgentDetail';

describe('AgentDetail - Inputs: empty schema fallback', () => {
  beforeEach(() => {
    mockAgent = { ...baseAgent, input_schema: [], output_schema: [] };
  });

  it('shows Instructions textarea fallback when input_schema is empty', () => {
    render(<AgentDetail />);
    expect(screen.getByPlaceholderText(/describe what you want the agent to do/i)).toBeInTheDocument();
    expect(screen.getByText('Instructions')).toBeInTheDocument();
  });

  it('inputs textarea updates state', async () => {
    render(<AgentDetail />);
    const textarea = screen.getByPlaceholderText(/describe what you want the agent to do/i);
    await userEvent.type(textarea, 'Research AI safety');
    expect(textarea).toHaveValue('Research AI safety');
  });
});

describe('AgentDetail - Inputs: schema-driven fields', () => {
  beforeEach(() => {
    mockAgent = {
      ...baseAgent,
      input_schema: [
        { name: 'topic', type: 'text', required: true, label: 'Research Topic', description: 'The subject to research', placeholder: 'e.g. AI market trends' },
        { name: 'depth', type: 'select', required: false, label: 'Depth', options: ['quick', 'standard', 'deep'] },
        { name: 'source_url', type: 'url', required: false, label: 'Source URL', placeholder: 'https://example.com' },
      ],
      output_schema: [],
    };
  });

  it('renders text input for type=text with label and placeholder', () => {
    render(<AgentDetail />);
    expect(screen.getByText('Research Topic')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. AI market trends')).toBeInTheDocument();
  });

  it('renders select for type=select with options', () => {
    render(<AgentDetail />);
    const select = screen.getByDisplayValue('quick');
    expect(select).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'quick' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'standard' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'deep' })).toBeInTheDocument();
  });

  it('renders url input for type=url', () => {
    render(<AgentDetail />);
    const urlInput = screen.getByPlaceholderText('https://example.com');
    expect(urlInput).toHaveAttribute('type', 'url');
  });

  it('marks required fields with asterisk', () => {
    render(<AgentDetail />);
    // Required field label wrapper should have a * span
    const labels = screen.getAllByText('*');
    expect(labels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows description helper text', () => {
    render(<AgentDetail />);
    expect(screen.getByText('The subject to research')).toBeInTheDocument();
  });

  it('does NOT show Instructions fallback when schema is provided', () => {
    render(<AgentDetail />);
    expect(screen.queryByText('INSTRUCTIONS')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/describe what you want the agent to do/i)).not.toBeInTheDocument();
  });
});

describe('AgentDetail - Outputs: schema-driven', () => {
  beforeEach(() => {
    mockAgent = {
      ...baseAgent,
      input_schema: [],
      output_schema: [
        { name: 'report', type: 'markdown', required: false, label: 'Research Report', description: 'Full analysis with findings' },
        { name: 'summary', type: 'text', required: false, label: 'Executive Summary' },
      ],
    };
  });

  it('renders output items from output_schema', () => {
    render(<AgentDetail />);
    expect(screen.getByText('Research Report')).toBeInTheDocument();
    expect(screen.getByText('Executive Summary')).toBeInTheDocument();
  });

  it('shows type badges for each output', () => {
    render(<AgentDetail />);
    expect(screen.getByText('markdown')).toBeInTheDocument();
    expect(screen.getByText('text')).toBeInTheDocument();
  });

  it('shows description when provided', () => {
    render(<AgentDetail />);
    expect(screen.getByText('Full analysis with findings')).toBeInTheDocument();
  });
});

describe('AgentDetail - Outputs: empty schema fallback', () => {
  beforeEach(() => {
    mockAgent = { ...baseAgent, input_schema: [], output_schema: [] };
  });

  it('shows forge inference message when output_schema is empty', () => {
    render(<AgentDetail />);
    expect(screen.getByText(/outputs will be inferred by forge/i)).toBeInTheDocument();
  });
});

describe('AgentDetail - Select default initialization', () => {
  beforeEach(() => {
    mockRunAgent.mutateAsync.mockReset();
    mockNavigate.mockReset();
    mockAgent = {
      ...baseAgent,
      input_schema: [
        { name: 'language', type: 'select', required: true, label: 'Language', options: ['Python', 'JavaScript', 'Rust'] },
        { name: 'path', type: 'text', required: true, label: 'Path', placeholder: '/some/path' },
      ],
      output_schema: [],
    };
  });

  it('initializes select inputs with first option so validation passes without interaction', async () => {
    mockRunAgent.mutateAsync.mockResolvedValue({ run_id: 'run-1' });
    render(<AgentDetail />);

    // Fill in the required text field
    const pathInput = screen.getByPlaceholderText('/some/path');
    await userEvent.type(pathInput, '/home/test');

    // Click Start Run without touching the select — should NOT show validation error
    const runButton = screen.getAllByText('Start Run')[0];
    await userEvent.click(runButton);

    // Should have navigated (run started), not shown a validation error
    expect(mockRunAgent.mutateAsync).toHaveBeenCalledWith({
      id: 'agent-1',
      inputs: { language: 'Python', path: '/home/test' },
    });
    expect(mockNavigate).toHaveBeenCalledWith('/runs/run-1');
  });

  it('does not override user-selected value with default', async () => {
    render(<AgentDetail />);

    // Change the select to a different value
    const select = screen.getByDisplayValue('Python');
    await userEvent.selectOptions(select, 'Rust');
    expect(select).toHaveValue('Rust');
  });

  it('submits selected run provider and model with the run request', async () => {
    mockRunAgent.mutateAsync.mockResolvedValue({ run_id: 'run-2' });
    render(<AgentDetail />);

    await userEvent.selectOptions(screen.getByLabelText('Run Provider'), 'codex');
    expect(screen.getByLabelText('Run Model')).toHaveValue('gpt-5-codex');

    await userEvent.selectOptions(screen.getByLabelText('Run Model'), 'gpt-5-mini');
    await userEvent.type(screen.getByPlaceholderText('/some/path'), '/tmp/project');
    await userEvent.click(screen.getAllByText('Start Run')[0]);

    expect(mockRunAgent.mutateAsync).toHaveBeenCalledWith({
      id: 'agent-1',
      inputs: { language: 'Python', path: '/tmp/project' },
      provider: 'codex',
      model: 'gpt-5-mini',
    });
  });
});

describe('AgentDetail - Per-step computer use display', () => {
  beforeEach(() => {
    mockAgent = { ...baseAgent, input_schema: [], output_schema: [] };
  });

  it('shows step names from object-shaped steps', () => {
    render(<AgentDetail />);
    expect(screen.getByText('Analyze code')).toBeInTheDocument();
    expect(screen.getByText('Write tests')).toBeInTheDocument();
    expect(screen.getByText('Create PR')).toBeInTheDocument();
  });

  it('shows CLI/Desktop badges per step', () => {
    render(<AgentDetail />);
    const cliBadges = screen.getAllByText('CLI');
    const desktopBadges = screen.getAllByText('Desktop');
    expect(cliBadges).toHaveLength(2);
    expect(desktopBadges).toHaveLength(1);
  });
});
