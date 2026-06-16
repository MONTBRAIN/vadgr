import { useMutation } from '@tanstack/react-query';
import { pairingApi } from '../api/pairing';
import type { PairResponse } from '../types/pairing';

// Mints a one-time pairing token. The token is never persisted client-side --
// it lives only in this mutation's `data` and is short-lived. Re-mint to refresh.
export function usePairing() {
  const mutation = useMutation<PairResponse, Error, void>({
    mutationFn: () => pairingApi.pair(),
  });

  return {
    mint: () => mutation.mutate(),
    data: mutation.data,
    error: mutation.error,
    isPending: mutation.isPending,
    isError: mutation.isError,
    reset: mutation.reset,
  };
}
