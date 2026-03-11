import { api } from './client';
import type { Agent, AgentCreate, AgentUpdate, RunStartResponse } from '../types';

export const agentsApi = {
  list: () => api.get<Agent[]>('/agents'),
  get: (id: string) => api.get<Agent>(`/agents/${id}`),
  create: (body: AgentCreate) => api.post<Agent>('/agents', body),
  update: (id: string, body: AgentUpdate) => api.put<Agent>(`/agents/${id}`, body),
  delete: (id: string) => api.delete<void>(`/agents/${id}`),
  deleteAll: () => api.delete<{ deleted: number }>('/agents'),
  run: (id: string, inputs: Record<string, unknown> = {}) =>
    api.post<RunStartResponse>(`/agents/${id}/run`, { inputs }),
  listRuns: (id: string) => api.get<import('../types').Run[]>(`/agents/${id}/runs`),
};
