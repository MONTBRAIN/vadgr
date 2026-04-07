/** Security layer: allowlist, rate limiting, sanitization, audit. */

import * as fs from "fs";
import * as path from "path";
import type { InboundMessage } from "./models.js";

const DANGEROUS_CHARS = /[;&|`$(){}]/g;
const MAX_MESSAGE_LENGTH = 2000;
const DEFAULT_RATE_LIMIT = 10;
const DEFAULT_RATE_WINDOW = 3600;

export const SILENT_REJECT = Symbol("SILENT_REJECT");

export interface SecurityConfig {
  allowedSenders: string[];
  rateLimit: number;
  rateWindow: number;
  auditLogPath?: string;
}

export function defaultSecurityConfig(): SecurityConfig {
  return {
    allowedSenders: [],
    rateLimit: DEFAULT_RATE_LIMIT,
    rateWindow: DEFAULT_RATE_WINDOW,
  };
}

type CheckResult = null | typeof SILENT_REJECT | string;

export class SecurityGuard {
  private config: SecurityConfig;
  private rateBuckets = new Map<string, number[]>();

  constructor(config: SecurityConfig) {
    this.config = config;
  }

  /**
   * Validate a message.
   * Returns null (OK), SILENT_REJECT (unknown sender), or error string.
   */
  check(message: InboundMessage): CheckResult {
    this.audit(message);

    // 1. Sender allowlist
    if (this.config.allowedSenders.length > 0) {
      if (!this.config.allowedSenders.includes(message.senderId)) {
        return SILENT_REJECT;
      }
    }

    // 2. Rate limiting
    if (this.isRateLimited(message.senderId)) {
      return "Slow down! Too many commands. Try again in a few minutes.";
    }

    // 3. Message length
    if (message.text.length > MAX_MESSAGE_LENGTH) {
      return `Message too long (max ${MAX_MESSAGE_LENGTH} chars).`;
    }

    return null;
  }

  sanitizeInput(value: string): string {
    return value.replace(DANGEROUS_CHARS, "").trim();
  }

  private isRateLimited(senderId: string): boolean {
    const now = Date.now() / 1000;
    const window = this.config.rateWindow;
    const limit = this.config.rateLimit;

    let bucket = this.rateBuckets.get(senderId);
    if (!bucket) {
      bucket = [];
      this.rateBuckets.set(senderId, bucket);
    }

    // Prune old entries
    const cutoff = now - window;
    while (bucket.length > 0 && (bucket[0] ?? 0) < cutoff) bucket.shift();

    if (bucket.length >= limit) return true;
    bucket.push(now);
    return false;
  }

  private audit(message: InboundMessage): void {
    if (!this.config.auditLogPath) return;
    const entry = {
      timestamp: message.timestamp.toISOString(),
      channel: message.channel,
      senderId: message.senderId,
      senderName: message.senderName,
      text: message.text.slice(0, 200),
    };
    const dir = path.dirname(this.config.auditLogPath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(this.config.auditLogPath, JSON.stringify(entry) + "\n");
  }
}
