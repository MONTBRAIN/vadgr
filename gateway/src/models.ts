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
}

export interface CommandResult {
  response: string;
  runId?: string;
  agentName?: string;
  isAsync: boolean;
}
