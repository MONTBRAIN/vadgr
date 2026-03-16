import { api } from './client';
import type { Agent, AgentCreate, AgentUpdate, ArtifactDescriptor, RunStartResponse } from '../types';

export const agentsApi = {
  list: () => api.get<Agent[]>('/agents'),
  get: (id: string) => api.get<Agent>(`/agents/${id}`),
  create: (body: AgentCreate) => api.post<Agent>('/agents', body),
  update: (id: string, body: AgentUpdate) => api.put<Agent>(`/agents/${id}`, body),
  delete: (id: string) => api.delete<void>(`/agents/${id}`),
  deleteAll: () => api.delete<{ deleted: number }>('/agents'),
  run: (
    id: string,
    inputs: Record<string, unknown> = {},
    provider?: string,
    model?: string,
  ) => api.post<RunStartResponse>(`/agents/${id}/run`, { inputs, provider, model }),
  uploadArtifact: async (id: string, fieldName: string, file: File): Promise<ArtifactDescriptor> => {
    const formData = new FormData();
    formData.append('field_name', fieldName);
    formData.append('file', file);
    const res = await fetch(`/api/agents/${id}/uploads`, {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      const message = data?.error?.message ?? `Request failed: ${res.status}`;
      throw new Error(message);
    }
    return data as ArtifactDescriptor;
  },
  listRuns: (id: string) => api.get<import('../types').Run[]>(`/agents/${id}/runs`),
};
