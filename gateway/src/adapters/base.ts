/** Abstract interface for all channel adapters. */

import type { InboundMessage, OutboundMessage } from "../models.js";

export type MessageHandler = (message: InboundMessage) => Promise<void>;

export interface ChannelAdapter {
  readonly name: string;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  sendMessage(message: OutboundMessage): Promise<void>;
  registerHandler(handler: MessageHandler): void;
}
