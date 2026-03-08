import { Card } from '../components/ui/Card';

export function Settings() {
  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-semibold text-text-primary">Settings</h1>

      <Card className="p-5 space-y-4">
        <h2 className="text-sm font-medium text-text-primary">Provider Configuration</h2>
        <p className="text-xs text-text-muted">
          Providers are configured in <code className="text-accent">providers.yaml</code> at the project root.
          Edit that file to add or modify provider configurations.
        </p>
        <div className="space-y-3">
          <SettingRow label="Default Provider" value="claude_code" />
          <SettingRow label="Provider Timeout" value="300s" />
          <SettingRow label="CORS Origins" value="http://localhost:3000" />
        </div>
      </Card>

      <Card className="p-5 space-y-4">
        <h2 className="text-sm font-medium text-text-primary">API Configuration</h2>
        <div className="space-y-3">
          <SettingRow label="Backend URL" value="http://127.0.0.1:8000" />
          <SettingRow label="Database" value="data/agent_forge.db (SQLite)" />
          <SettingRow label="API Version" value="0.1.0" />
        </div>
      </Card>

      <Card className="p-5 space-y-4">
        <h2 className="text-sm font-medium text-text-primary">About</h2>
        <p className="text-xs text-text-secondary">
          Agent Forge is an agent-agnostic meta-framework for creating agentic workflows.
          This is the Phase A frontend covering Agents and Runs management.
        </p>
      </Card>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50">
      <span className="text-sm text-text-secondary">{label}</span>
      <span className="text-sm text-text-primary font-mono">{value}</span>
    </div>
  );
}
