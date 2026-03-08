import { api } from './client';
import type { Run } from '../types';

export const runsApi = {
  list: (status?: string) =>
    api.get<Run[]>(status ? `/runs?status=${status}` : '/runs'),
  get: (id: string) => api.get<Run>(`/runs/${id}`),
  cancel: (id: string) => api.post<Run>(`/runs/${id}/cancel`),
  approve: (id: string) => api.post<Run>(`/runs/${id}/approve`),
};
