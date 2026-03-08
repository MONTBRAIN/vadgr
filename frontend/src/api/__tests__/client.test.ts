import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '../client';

describe('api client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('makes GET requests', async () => {
    const mockData = [{ id: '1', name: 'Agent' }];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockData),
    }) as typeof fetch;

    const result = await api.get('/agents');
    expect(result).toEqual(mockData);
    expect(fetch).toHaveBeenCalledWith('/api/agents', expect.objectContaining({
      headers: { 'Content-Type': 'application/json' },
    }));
  });

  it('makes POST requests with body', async () => {
    const body = { name: 'New Agent' };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: () => Promise.resolve({ id: '1', ...body }),
    }) as typeof fetch;

    await api.post('/agents', body);
    expect(fetch).toHaveBeenCalledWith('/api/agents', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(body),
    }));
  });

  it('handles 204 no content', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    }) as typeof fetch;

    const result = await api.delete('/agents/1');
    expect(result).toBeUndefined();
  });

  it('throws on error response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ error: { message: 'Not found' } }),
    }) as typeof fetch;

    await expect(api.get('/agents/missing')).rejects.toThrow('Not found');
  });
});
