import { useQuery } from '@tanstack/react-query';
import { providersApi } from '../api/providers';

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: providersApi.list,
    staleTime: 5 * 60 * 1000, // providers rarely change, cache 5 min
  });
}
