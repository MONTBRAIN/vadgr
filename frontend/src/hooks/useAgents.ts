import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi } from '../api/agents';
import type { AgentCreate, AgentUpdate } from '../types';

export function useAgents() {
  return useQuery({ queryKey: ['agents'], queryFn: agentsApi.list });
}

export function useAgent(id: string) {
  return useQuery({ queryKey: ['agents', id], queryFn: () => agentsApi.get(id), enabled: !!id });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentCreate) => agentsApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AgentUpdate }) => agentsApi.update(id, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['agents'] });
      qc.invalidateQueries({ queryKey: ['agents', vars.id] });
    },
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => agentsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useRunAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, inputs }: { id: string; inputs: Record<string, unknown> }) =>
      agentsApi.run(id, inputs),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  });
}
