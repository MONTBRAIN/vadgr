/** Unified message models for the gateway. Channel-agnostic. */

export enum MessageType {
  TEXT = "text",
  IMAGE = "image",
  AUDIO = "audio",
  DOCUMENT = "document",
  UNKNOWN = "unknown",
}

export interface InboundMessage {
  channel: string;
  chatId: string;
  senderId: string;
  senderName: string;
  text: string;
  messageType: MessageType;
  timestamp: Date;
  raw: Record<string, unknown>;
}

export interface OutboundMessage {
  chatId: string;
  text: string;
  embed?: any;  // discord.js EmbedBuilder -- typed as any to stay adapter-agnostic
}

export interface CommandResult {
  response: string;
  runId?: string;
  agentName?: string;
  machineName?: string;
  isAsync: boolean;
}

/** Transport-agnostic agent API. Implemented by VadgrAPIClient (single-machine)
 *  and MultiMachineAPI (multi-machine via WebSocket). */
export interface AgentAPI {
  listAgents(): Promise<Record<string, unknown>[]>;
  runAgent(agentId: string, inputs: Record<string, string>): Promise<Record<string, unknown>>;
  listRuns(): Promise<Record<string, unknown>[]>;
  getRun(runId: string): Promise<Record<string, unknown>>;
  cancelRun(runId: string): Promise<Record<string, unknown>>;
  resumeRun(runId: string): Promise<Record<string, unknown>>;
  getRunLogs(runId: string): Promise<Record<string, unknown>[]>;
}
