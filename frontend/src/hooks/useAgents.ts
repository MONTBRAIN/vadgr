import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi } from '../api/agents';
import { BUSY_STATUSES } from '../types';
import type { AgentCreate, AgentUpdate } from '../types';

export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
    refetchInterval: (query) => {
      const agents = query.state.data;
      if (!Array.isArray(agents)) return false;
      const busy = agents.some((a) => BUSY_STATUSES.has(a.status));
      return busy ? 3000 : false;
    },
  });
}

export function useAgent(id: string) {
  return useQuery({
    queryKey: ['agents', id],
    queryFn: () => agentsApi.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return BUSY_STATUSES.has(status) ? 3000 : false;
    },
  });
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
    mutationFn: ({
      id,
      inputs,
      provider,
      model,
    }: {
      id: string;
      inputs: Record<string, unknown>;
      provider?: string;
      model?: string;
    }) => agentsApi.run(id, inputs, provider, model),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  });
}

export function useUploadAgentArtifact() {
  return useMutation({
    mutationFn: ({
      id,
      fieldName,
      file,
    }: {
      id: string;
      fieldName: string;
      file: File;
    }) => agentsApi.uploadArtifact(id, fieldName, file),
  });
}

export function useExportAgentPackage() {
  return useMutation({
    mutationFn: (id: string) => agentsApi.exportPackage(id),
  });
}

export function useImportAgentPackage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => agentsApi.importPackage(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}
