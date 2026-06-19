import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { usePairing } from '../usePairing';
import { pairingApi } from '../../api/pairing';

vi.mock('../../api/pairing', () => ({
  pairingApi: { pair: vi.fn() },
}));

const pairMock = pairingApi.pair as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('usePairing', () => {
  beforeEach(() => {
    pairMock.mockReset();
  });

  it('mints a token and exposes the PairResponse on success', async () => {
    const response = { host: 'box.ts.net', port: 8000, pairing_token: 'tok', machine_name: 'Box' };
    pairMock.mockResolvedValue(response);

    const { result } = renderHook(() => usePairing(), { wrapper });
    expect(result.current.isPending).toBe(false);

    act(() => result.current.mint());

    await waitFor(() => expect(result.current.data).toEqual(response));
    expect(result.current.isError).toBe(false);
  });

  it('surfaces errors', async () => {
    pairMock.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => usePairing(), { wrapper });
    act(() => result.current.mint());

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('boom');
  });
});
