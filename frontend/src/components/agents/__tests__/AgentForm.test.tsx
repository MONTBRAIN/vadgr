import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

// Mock hooks
vi.mock('../../../hooks/useAgents', () => ({
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('../../../hooks/useProviders', () => ({
  useProviders: () => ({
    data: [
      {
        id: 'claude_code',
        name: 'Claude Code',
        models: [
          { id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6' },
          { id: 'claude-opus-4-6', name: 'Claude Opus 4.6' },
          { id: 'claude-haiku-4-5', name: 'Claude Haiku 4.5' },
        ],
      },
      {
        id: 'codex',
        name: 'OpenAI Codex CLI',
        models: [
          { id: 'o4-mini', name: 'o4-mini' },
          { id: 'o3', name: 'o3' },
        ],
      },
      {
        id: 'aider',
        name: 'Aider',
        models: [
          { id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6' },
          { id: 'gpt-4.1', name: 'GPT-4.1' },
        ],
      },
    ],
  }),
}));

import { AgentForm } from '../AgentForm';

describe('AgentForm - Model options', () => {
  it('includes Claude models in claude_code model options', () => {
    render(<AgentForm />);

    // Default provider is claude_code
    const modelSelect = screen.getByLabelText('Model');
    const options = Array.from(modelSelect.querySelectorAll('option'));
    const labels = options.map((o) => o.textContent);

    expect(labels).toContain('Claude Sonnet 4.6');
    expect(labels).toContain('Claude Opus 4.6');
    expect(labels).toContain('Claude Haiku 4.5');
  });

  it('switches models when provider changes', async () => {
    render(<AgentForm />);

    // Switch to Codex provider
    const providerSelect = screen.getByLabelText('Provider');
    await userEvent.selectOptions(providerSelect, 'codex');

    // Check model dropdown has Codex models
    const modelSelect = screen.getByLabelText('Model');
    const options = Array.from(modelSelect.querySelectorAll('option'));
    const labels = options.map((o) => o.textContent);

    expect(labels).toContain('o4-mini');
    expect(labels).toContain('o3');
    expect(labels).not.toContain('Claude Haiku 4.5');
  });
});

describe('AgentForm - Per-step computer use', () => {
  it('adds a step defaulting to CLI mode (computer_use=false)', async () => {
    render(<AgentForm />);

    const input = screen.getByPlaceholderText('Add a step and press Enter');
    await userEvent.type(input, 'Research sources{enter}');

    // Step should appear with CLI toggle button
    expect(screen.getByText('Research sources')).toBeInTheDocument();
    const toggleButtons = screen.getAllByRole('button').filter(b => b.textContent?.includes('CLI'));
    expect(toggleButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('toggles a step from CLI to Desktop', async () => {
    render(<AgentForm />);

    const input = screen.getByPlaceholderText('Add a step and press Enter');
    await userEvent.type(input, 'Create PR{enter}');

    // Find the CLI toggle button (not the legend text)
    const cliButton = screen.getAllByRole('button').find(b => b.textContent?.trim() === 'CLI');
    expect(cliButton).toBeTruthy();

    // Click to toggle to Desktop
    await userEvent.click(cliButton!);
    const desktopButton = screen.getAllByRole('button').find(b => b.textContent?.trim() === 'Desktop');
    expect(desktopButton).toBeTruthy();
  });

  it('shows computer use banner when any step has Desktop enabled', async () => {
    render(<AgentForm />);

    const input = screen.getByPlaceholderText('Add a step and press Enter');
    await userEvent.type(input, 'Browse web{enter}');

    // No banner initially
    expect(screen.queryByText(/Computer use enabled/)).not.toBeInTheDocument();

    // Toggle to Desktop
    const cliButton = screen.getAllByRole('button').find(b => b.textContent?.trim() === 'CLI');
    await userEvent.click(cliButton!);

    // Banner should appear
    expect(screen.getByText(/Computer use enabled/)).toBeInTheDocument();
  });

  it('shows CLI/Desktop legend when steps exist', async () => {
    render(<AgentForm />);

    const input = screen.getByPlaceholderText('Add a step and press Enter');
    await userEvent.type(input, 'Step one{enter}');

    expect(screen.getByText(/terminal/)).toBeInTheDocument();
    expect(screen.getByText(/take control/)).toBeInTheDocument();
  });

  it('loads existing agent with object steps correctly', () => {
    const agent = {
      id: 'test-1',
      name: 'Test',
      description: 'desc',
      type: 'agent' as const,
      status: 'ready' as const,
      forge_path: '',
      steps: [
        { name: 'CLI step', computer_use: false },
        { name: 'Desktop step', computer_use: true },
      ],
      samples: [],
      input_schema: [],
      output_schema: [],
      computer_use: true,
      forge_config: {},
      provider: 'claude_code',
      model: 'claude-sonnet-4-6',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    };

    render(<AgentForm agent={agent} />);

    expect(screen.getByText('CLI step')).toBeInTheDocument();
    expect(screen.getByText('Desktop step')).toBeInTheDocument();
    // Toggle buttons: one should say CLI, one should say Desktop
    const toggleButtons = screen.getAllByRole('button').filter(
      b => b.textContent?.trim() === 'CLI' || b.textContent?.trim() === 'Desktop'
    );
    const cliButtons = toggleButtons.filter(b => b.textContent?.trim() === 'CLI');
    const desktopButtons = toggleButtons.filter(b => b.textContent?.trim() === 'Desktop');
    expect(cliButtons).toHaveLength(1);
    expect(desktopButtons).toHaveLength(1);
  });
});
