import { describe, it, expect, vi, beforeEach } from 'vitest';
import { pairingApi } from '../pairing';

describe('pairingApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('POSTs to /api/auth/pair and returns the PairResponse', async () => {
    const body = {
      host: 'box.ts.net',
      port: 8000,
      pairing_token: 'tok',
      machine_name: 'Box',
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    }) as unknown as typeof fetch;

    const result = await pairingApi.pair();
    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/pair',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result).toEqual(body);
  });

  it('throws the backend error message on failure', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: () => Promise.resolve({ error: { message: 'Tailscale isn\'t available' } }),
    }) as unknown as typeof fetch;

    await expect(pairingApi.pair()).rejects.toThrow('Tailscale');
  });
});
