import { api } from './client';

export interface PairResponse {
  host: string;
  port: number;
  token: string;
  machine_name: string;
}

export const authApi = {
  pair: () => api.post<PairResponse>('/auth/pair', {}),
};
