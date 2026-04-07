/** Abstract interface for all channel adapters. */

import type { InboundMessage, OutboundMessage } from "../models.js";

export type MessageHandler = (message: InboundMessage) => Promise<void>;

/** Returns true if the sender has an active conversational session. */
export type SessionChecker = (senderId: string) => boolean;

export interface ChannelAdapter {
  readonly name: string;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  sendMessage(message: OutboundMessage): Promise<void>;
  registerHandler(handler: MessageHandler): void;
  /** Let the adapter know about active sessions so it can forward follow-ups. */
  setSessionChecker?(checker: SessionChecker): void;
}
