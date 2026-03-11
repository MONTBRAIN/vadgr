import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: 'agent-1' }),
  useNavigate: () => mockNavigate,
}));

// Mock hooks
const mockRunAgent = { mutateAsync: vi.fn(), isPending: false };
vi.mock('../../hooks/useAgents', () => ({
  useAgent: () => ({
    data: {
      id: 'agent-1',
      name: 'Test Agent',
      description: 'A test agent',
      status: 'ready',
      type: 'agent',
      provider: 'anthropic',
      model: 'claude-sonnet-4-6',
      computer_use: true,
      created_at: '2025-01-01T00:00:00Z',
      steps: [
        { name: 'Analyze code', computer_use: false },
        { name: 'Write tests', computer_use: false },
        { name: 'Create PR', computer_use: true },
      ],
      input_schema: [],
      output_schema: [],
    },
    isLoading: false,
  }),
  useDeleteAgent: () => ({ mutateAsync: vi.fn() }),
  useRunAgent: () => mockRunAgent,
}));

import { AgentDetail } from '../AgentDetail';

describe('AgentDetail - Run Agent section', () => {
  it('shows a task textarea when run form is opened and no input_schema exists', async () => {
    render(<AgentDetail />);
    const startBtn = screen.getByText('Start Run');
    await userEvent.click(startBtn);

    // Should show a task textarea, NOT "No inputs required"
    expect(screen.getByPlaceholderText(/describe what.*agent should do/i)).toBeInTheDocument();
    expect(screen.queryByText('No inputs required')).not.toBeInTheDocument();
  });

  it('task textarea updates the inputs for running', async () => {
    render(<AgentDetail />);
    await userEvent.click(screen.getByText('Start Run'));

    const textarea = screen.getByPlaceholderText(/describe what.*agent should do/i);
    await userEvent.type(textarea, 'Research AI safety');
    expect(textarea).toHaveValue('Research AI safety');
  });
});

describe('AgentDetail - Per-step computer use display', () => {
  it('shows step names from object-shaped steps', () => {
    render(<AgentDetail />);

    expect(screen.getByText('Analyze code')).toBeInTheDocument();
    expect(screen.getByText('Write tests')).toBeInTheDocument();
    expect(screen.getByText('Create PR')).toBeInTheDocument();
  });

  it('shows CLI/Desktop badges per step', () => {
    render(<AgentDetail />);

    // 2 CLI steps + 1 Desktop step
    const cliBadges = screen.getAllByText('CLI');
    const desktopBadges = screen.getAllByText('Desktop');
    expect(cliBadges).toHaveLength(2);
    expect(desktopBadges).toHaveLength(1);
  });
});
