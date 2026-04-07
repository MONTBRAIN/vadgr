/** HTTP client for the Vadgr API. */

const DEFAULT_TIMEOUT = 30_000;
const MAX_RETRIES = 3;
const RETRY_BACKOFF_BASE = 1000;

export class VadgrAPIClient {
  private baseUrl: string;

  constructor(baseUrl = "http://localhost:8000") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async listAgents(): Promise<Record<string, unknown>[]> {
    return this.requestWithRetry(`${this.baseUrl}/api/agents`);
  }

  async runAgent(agentId: string, inputs: Record<string, string>): Promise<Record<string, unknown>> {
    return this.requestWithRetry(`${this.baseUrl}/api/agents/${agentId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs }),
    });
  }

  async listRuns(): Promise<Record<string, unknown>[]> {
    return this.requestWithRetry(`${this.baseUrl}/api/runs`);
  }

  async getRun(runId: string): Promise<Record<string, unknown>> {
    return this.requestWithRetry(`${this.baseUrl}/api/runs/${runId}`);
  }

  async cancelRun(runId: string): Promise<Record<string, unknown>> {
    return this.requestWithRetry(`${this.baseUrl}/api/runs/${runId}/cancel`, { method: "POST" });
  }

  async resumeRun(runId: string): Promise<Record<string, unknown>> {
    return this.requestWithRetry(`${this.baseUrl}/api/runs/${runId}/resume`, { method: "POST" });
  }

  async getRunLogs(runId: string): Promise<Record<string, unknown>[]> {
    return this.requestWithRetry(`${this.baseUrl}/api/runs/${runId}/logs`);
  }

  private async requestWithRetry(url: string, init?: RequestInit): Promise<any> {
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      const resp = await fetch(url, {
        ...init,
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT),
      });
      if (resp.ok) return resp.json();
      if (resp.status >= 500 && attempt < MAX_RETRIES - 1) {
        await new Promise((r) => setTimeout(r, RETRY_BACKOFF_BASE * 2 ** attempt));
        continue;
      }
      throw new Error(`API error ${resp.status}: ${await resp.text()}`);
    }
  }
}
