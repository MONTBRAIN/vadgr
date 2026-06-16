import type { PairResponse } from '../types/pairing';

// Pure builder for the cross-repo `vadgr://pair` deep link. The param names
// MUST match what vadgr-mobile's scanner reads and the CLI's build_pair_uri:
// host / port / token / name.
export function buildPairUri(p: PairResponse): string {
  const q = new URLSearchParams({
    host: p.host,
    port: String(p.port),
    token: p.pairing_token,
    name: p.machine_name,
  });
  return `vadgr://pair?${q.toString()}`;
}
