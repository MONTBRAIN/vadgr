import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dependencies
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({ theme: 'dark', toggle: vi.fn() }),
}));

vi.mock('../../hooks/useProviders', () => ({
  useProviders: () => ({ data: [{ id: 'claude_code' }] }),
}));

vi.mock('../../api/agents', () => ({
  agentsApi: { deleteAll: vi.fn() },
}));

vi.mock('../../api/runs', () => ({
  runsApi: { deleteAll: vi.fn() },
}));

// Mock api client with controllable responses
const mockGet = vi.fn();
const mockPut = vi.fn();
vi.mock('../../api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
  },
}));

import { Settings } from '../Settings';

describe('Settings - Computer Use Toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue({ enabled: false, cache_enabled: true });
    mockPut.mockResolvedValue({ enabled: true, cache_enabled: true });
  });

  it('shows "Disabled" status when computer use is off', async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText('Disabled')).toBeTruthy();
    });
  });

  it('shows "Active" status with solid green dot when computer use is on', async () => {
    mockGet.mockResolvedValue({ enabled: true, cache_enabled: true });
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeTruthy();
    });
  });

  it('shows "Activating..." with pulsing indicator while enabling', async () => {
    // Make the PUT hang so we can observe the loading state
    let resolvePut: (v: unknown) => void;
    mockPut.mockReturnValue(new Promise((r) => { resolvePut = r; }));

    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText('Disabled')).toBeTruthy();
    });

    const toggle = screen.getByRole('button', { name: /computer use toggle/i });
    await userEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByText('Activating...')).toBeTruthy();
    });

    // Verify the ping animation element exists
    const pingEl = document.querySelector('.animate-ping');
    expect(pingEl).toBeTruthy();

    // Resolve and verify it switches to Active
    resolvePut!({ enabled: true, cache_enabled: true });
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeTruthy();
    });
  });

  it('shows "Deactivating..." with pulsing indicator while disabling', async () => {
    mockGet.mockResolvedValue({ enabled: true, cache_enabled: true });
    let resolvePut: (v: unknown) => void;
    mockPut.mockReturnValue(new Promise((r) => { resolvePut = r; }));

    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeTruthy();
    });

    const toggle = screen.getByRole('button', { name: /computer use toggle/i });
    await userEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByText('Deactivating...')).toBeTruthy();
    });

    resolvePut!({ enabled: false, cache_enabled: true });
    await waitFor(() => {
      expect(screen.getByText('Disabled')).toBeTruthy();
    });
  });

  it('shows error message when toggle fails', async () => {
    mockPut.mockRejectedValue(new Error('Setup failed'));

    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText('Disabled')).toBeTruthy();
    });

    const toggle = screen.getByRole('button', { name: /computer use toggle/i });
    await userEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByText(/setup failed/i)).toBeTruthy();
    });
  });

  it('has no ping animation when status is Active (solid dot only)', async () => {
    mockGet.mockResolvedValue({ enabled: true, cache_enabled: true });
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeTruthy();
    });
    const pingEl = document.querySelector('.animate-ping');
    expect(pingEl).toBeNull();
  });
});
