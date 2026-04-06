// @vitest-environment node
import { describe, it, expect } from 'vitest';
import config from '../../vite.config';

describe('vite.config', () => {
  it('server.host is set so the dev server is reachable outside 127.0.0.1', () => {
    expect((config as any).server?.host).toBeTruthy();
  });
});
