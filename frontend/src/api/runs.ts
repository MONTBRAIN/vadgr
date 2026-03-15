import { api } from './client';
import type { Run, WSEvent } from '../types';

export const runsApi = {
  list: (status?: string) =>
    api.get<Run[]>(status ? `/runs?status=${status}` : '/runs'),
  get: (id: string) => api.get<Run>(`/runs/${id}`),
  cancel: (id: string) => api.post<Run>(`/runs/${id}/cancel`),
  approve: (id: string) => api.post<Run>(`/runs/${id}/approve`),
  deleteAll: () => api.delete<{ deleted: number }>('/runs'),
  getLogs: (id: string) => api.get<WSEvent[]>(`/runs/${id}/logs`),
  getStepLog: (id: string, file: string) => api.get<WSEvent[]>(`/runs/${id}/logs/${file}`),
  getOutput: async (runId: string, fieldName: string): Promise<string> => {
    const res = await fetch(`/api/runs/${runId}/outputs/${fieldName}`);
    if (!res.ok) throw new Error(`Failed to fetch output: ${res.statusText}`);
    return res.text();
  },
};
