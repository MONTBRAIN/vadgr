import { api } from './client';

export interface ProviderModel {
  id: string;
  name: string;
}

export interface Provider {
  id: string;
  name: string;
  models: ProviderModel[];
}

export const providersApi = {
  list: () => api.get<Provider[]>('/providers'),
};
