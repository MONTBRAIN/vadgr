import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { runsApi } from '../api/runs';

export function useRuns(status?: string) {
  return useQuery({ queryKey: ['runs', status], queryFn: () => runsApi.list(status) });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: ['runs', id],
    queryFn: () => runsApi.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const run = query.state.data;
      if (run && (run.status === 'completed' || run.status === 'failed')) return false;
      return 3000;
    },
  });
}

export function useCancelRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => runsApi.cancel(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['runs'] });
      qc.invalidateQueries({ queryKey: ['runs', id] });
    },
  });
}

export function useApproveRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => runsApi.approve(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['runs'] });
      qc.invalidateQueries({ queryKey: ['runs', id] });
    },
  });
}
