import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PairDeviceCard } from '../PairDeviceCard';
import { usePairing } from '../../../hooks/usePairing';

vi.mock('../../../hooks/usePairing', () => ({
  usePairing: vi.fn(),
}));

const usePairingMock = usePairing as unknown as ReturnType<typeof vi.fn>;

const idle = {
  mint: vi.fn(),
  data: undefined,
  error: null,
  isPending: false,
  isError: false,
  reset: vi.fn(),
};

beforeEach(() => {
  usePairingMock.mockReset();
});

describe('PairDeviceCard', () => {
  it('idle renders the Pair button', () => {
    usePairingMock.mockReturnValue({ ...idle });
    render(<PairDeviceCard />);
    expect(screen.getByText('Mobile Pairing')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pair device' })).toBeInTheDocument();
  });

  it('clicking Pair triggers mint', () => {
    const mint = vi.fn();
    usePairingMock.mockReturnValue({ ...idle, mint });
    render(<PairDeviceCard />);
    fireEvent.click(screen.getByRole('button', { name: 'Pair device' }));
    expect(mint).toHaveBeenCalledOnce();
  });

  it('success renders the QR with the vadgr://pair URI + raw token', () => {
    const data = {
      host: 'box.tailnet.ts.net',
      port: 8000,
      pairing_token: 'secret-token-xyz',
      machine_name: 'Work Box',
    };
    usePairingMock.mockReturnValue({ ...idle, data });
    const { container } = render(<PairDeviceCard />);

    // QR encodes the deep link incl. the token.
    const svg = container.querySelector('svg[value]') ?? container.querySelector('svg');
    expect(svg).toBeTruthy();
    // Raw token shown for manual entry.
    expect(screen.getByText('secret-token-xyz')).toBeInTheDocument();
    expect(screen.getByText(/box.tailnet.ts.net:8000/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
  });

  it('transport-unavailable error renders the Tailscale hint + Retry', () => {
    usePairingMock.mockReturnValue({
      ...idle,
      isError: true,
      error: new Error("Tailscale isn't available to pair over your tailnet"),
    });
    render(<PairDeviceCard />);
    expect(screen.getByRole('alert').textContent).toMatch(/Tailscale isn't available/i);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('generic error renders the message + Retry', () => {
    usePairingMock.mockReturnValue({
      ...idle,
      isError: true,
      error: new Error('Something broke'),
    });
    render(<PairDeviceCard />);
    expect(screen.getByRole('alert').textContent).toMatch(/Something broke/);
  });
});
