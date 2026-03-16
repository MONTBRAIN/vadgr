import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: 'run-1' }),
  useNavigate: () => mockNavigate,
}));

const mockRun = {
  id: 'run-1',
  project_id: null,
  agent_id: 'agent-1',
  status: 'completed',
  inputs: {},
  outputs: {},
  provider: 'codex',
  model: 'gpt-5-codex',
  log_path: null,
  started_at: '2026-03-15T10:00:00Z',
  completed_at: '2026-03-15T10:01:00Z',
};

const mockAgent = {
  id: 'agent-1',
  name: 'Research Agent',
  description: 'Researches topics',
  status: 'ready',
  type: 'agent',
  provider: 'claude_code',
  model: 'claude-sonnet-4-6',
  computer_use: false,
  created_at: '2026-03-15T00:00:00Z',
  updated_at: '2026-03-15T00:00:00Z',
  forge_path: '',
  forge_config: {},
  samples: [],
  steps: [],
  input_schema: [],
  output_schema: [],
};

vi.mock('../../hooks/useRuns', () => ({
  useRun: () => ({ data: mockRun, isLoading: false }),
  useCancelRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('../../hooks/useAgents', () => ({
  useAgent: () => ({ data: mockAgent, isLoading: false }),
}));

vi.mock('../../hooks/useWebSocket', () => ({
  useRunWebSocket: () => ({ events: [] }),
}));

vi.mock('../../components/runs/RunTimeline', () => ({
  RunTimeline: () => <div>Timeline</div>,
}));

vi.mock('../../components/runs/RunLog', () => ({
  RunLog: () => <div>Log</div>,
}));

import { RunViewer } from '../RunViewer';

describe('RunViewer', () => {
  it('shows the effective run provider and model', () => {
    render(<RunViewer />);

    expect(screen.getByText('codex')).toBeInTheDocument();
    expect(screen.getByText('gpt-5-codex')).toBeInTheDocument();
    expect(screen.queryByText('claude_code')).not.toBeInTheDocument();
    expect(screen.queryByText('claude-sonnet-4-6')).not.toBeInTheDocument();
  });
});
