import { describe, it, expect } from 'vitest';
import { buildPairUri } from '../pairUri';

const base = {
  host: 'my-box.tailnet-1234.ts.net',
  port: 8000,
  pairing_token: 'abc-123',
  machine_name: 'Work Box',
};

describe('buildPairUri', () => {
  it('builds a vadgr://pair URI with all params', () => {
    const uri = buildPairUri(base);
    expect(uri.startsWith('vadgr://pair?')).toBe(true);
    const q = new URLSearchParams(uri.split('?')[1]);
    expect(q.get('host')).toBe('my-box.tailnet-1234.ts.net');
    expect(q.get('port')).toBe('8000');
    expect(q.get('token')).toBe('abc-123');
    expect(q.get('name')).toBe('Work Box');
  });

  it('URL-encodes the machine name', () => {
    const uri = buildPairUri({ ...base, machine_name: 'My Box & Co' });
    expect(uri).toContain('name=My+Box+%26+Co');
  });

  it('never embeds loopback', () => {
    expect(buildPairUri(base)).not.toContain('127.0.0.1');
  });
});
