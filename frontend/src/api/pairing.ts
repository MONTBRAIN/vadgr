import { api } from './client';
import type { PairResponse } from '../types/pairing';

export const pairingApi = {
  // BASE_URL already prefixes /api.
  pair: () => api.post<PairResponse>('/auth/pair'),
};
