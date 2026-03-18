export interface SchemaField {
  name: string;
  type: 'text' | 'url' | 'textarea' | 'select' | 'number' | 'boolean' | 'file' | 'archive' | 'directory' | 'markdown' | 'json';
  required: boolean;
  label?: string;
  description?: string;
  placeholder?: string;
  options?: string[];
  accept?: string[];
  mime_types?: string[];
  max_size_mb?: number;
  multiple?: boolean;
}

export interface ArtifactDescriptor {
  kind: 'file' | 'archive' | 'directory';
  path: string;
  filename: string;
  mime_type?: string;
}

export interface StepDefinition {
  name: string;
  computer_use: boolean;
}

export type AgentStatus = 'creating' | 'updating' | 'importing' | 'ready' | 'error';
export const BUSY_STATUSES = new Set<AgentStatus>(['creating', 'updating', 'importing']);

export interface Agent {
  id: string;
  name: string;
  description: string;
  type: 'agent' | 'approval' | 'input' | 'output';
  status: AgentStatus;
  forge_path: string;
  steps: StepDefinition[];
  samples: string[];
  input_schema: SchemaField[];
  output_schema: SchemaField[];
  computer_use: boolean;
  forge_config: Record<string, unknown>;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  name: string;
  description?: string;
  steps?: StepDefinition[];
  samples?: string[];
  computer_use?: boolean;
  provider?: string;
  model?: string;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  status?: string;
  steps?: StepDefinition[];
  samples?: string[];
  input_schema?: SchemaField[];
  output_schema?: SchemaField[];
  computer_use?: boolean;
  provider?: string;
  model?: string;
}

export interface Run {
  id: string;
  project_id: string | null;
  agent_id: string | null;
  status: 'queued' | 'running' | 'awaiting_approval' | 'completed' | 'failed';
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  provider: string | null;
  model: string | null;
  log_path: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentRun {
  id: string;
  run_id: string;
  node_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  logs: string;
  duration_ms: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface RunStartResponse {
  run_id: string;
  status: string;
}

export interface WSEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}
