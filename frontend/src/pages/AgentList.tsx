import type { ChangeEvent } from 'react';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAgents, useImportAgentPackage } from '../hooks/useAgents';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { StatusBadge, ProviderBadge } from '../components/ui/Badge';
import { PixelRobot, PixelPlay, PixelList } from '../components/ui/PixelIcon';

export function AgentList() {
  const navigate = useNavigate();
  const { data: agents = [], isLoading } = useAgents();
  const importAgentPackage = useImportAgentPackage();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState('');
  const [view, setView] = useState<'grid' | 'list'>('grid');

  const filtered = agents.filter(
    (a) =>
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.description.toLowerCase().includes(search.toLowerCase()),
  );

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleImportChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      await importAgentPackage.mutateAsync(file);
    } finally {
      event.target.value = '';
    }
  };

  return (
    <div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={handleImportChange}
      />
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="font-heading text-[28px] font-semibold text-text-primary tracking-tight mb-1">Agents</h1>
          <p className="font-body text-[13px] text-text-muted font-light">{agents.length} agents configured</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={handleImportClick} disabled={importAgentPackage.isPending}>
            {importAgentPackage.isPending ? 'Importing...' : 'Import Agent'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setView((v) => (v === 'grid' ? 'list' : 'grid'))}>
            <PixelList size={12} color="var(--color-text-muted)" /> {view === 'grid' ? 'List' : 'Grid'}
          </Button>
          <Button size="sm" onClick={() => navigate('/agents/new')}>+ New Agent</Button>
        </div>
      </div>

      {search !== undefined && (
        <input
          type="text"
          placeholder="Search agents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-sm px-4 py-2.5 bg-bg-input border border-border rounded-[10px] text-sm text-text-primary placeholder:text-text-muted mb-6 transition-colors focus:border-accent"
        />
      )}

      {isLoading ? (
        <div className="text-sm text-text-muted">Loading...</div>
      ) : filtered.length > 0 ? (
        view === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filtered.map((agent) => (
              <Card
                key={agent.id}
                hoverable
                className="px-7 py-6 flex flex-col gap-3.5"
                onClick={() => navigate(`/agents/${agent.id}`)}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-heading text-base font-semibold text-text-primary mb-1.5">{agent.name}</h3>
                    <div className="flex gap-2 items-center">
                      <StatusBadge status={agent.status} />
                      <span className="font-body text-[10px] font-semibold uppercase tracking-wider text-accent">{agent.type}</span>
                    </div>
                  </div>
                  <PixelRobot size={20} color="var(--color-accent)" hole="var(--color-bg-primary)" />
                </div>
                <p className="font-body text-xs text-text-muted font-light leading-relaxed flex-1">
                  {agent.description || 'No description'}
                </p>
                <div className="flex items-center justify-between pt-3 border-t border-border">
                  <ProviderBadge provider={agent.provider} />
                  <Button
                    size="sm"
                    disabled={agent.status !== 'ready'}
                    onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}`); }}
                  >
                    <PixelPlay size={10} color="var(--color-bg-primary)" /> Run
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Card className="overflow-hidden">
            <div className="grid grid-cols-[2.5fr_1fr_1fr_0.8fr_1.2fr_1fr] px-7 py-3 border-b border-border">
              {['Name', 'Status', 'Provider', 'Type', 'Model', 'Updated'].map((h) => (
                <span key={h} className="font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider">{h}</span>
              ))}
            </div>
            {filtered.map((agent, i) => (
              <div
                key={agent.id}
                className="grid grid-cols-[2.5fr_1fr_1fr_0.8fr_1.2fr_1fr] px-7 py-3.5 items-center cursor-pointer transition-colors hover:bg-hover-bg"
                style={{ background: i % 2 === 1 ? 'var(--color-hover-bg)' : 'transparent' }}
                onClick={() => navigate(`/agents/${agent.id}`)}
              >
                <span className="font-body text-[13px] text-text-primary">{agent.name}</span>
                <StatusBadge status={agent.status} />
                <ProviderBadge provider={agent.provider} />
                <span className="font-body text-[10px] font-semibold uppercase tracking-wider text-accent">{agent.type}</span>
                <span className="font-mono text-[10px] text-text-muted">{agent.model}</span>
                <span className="font-body text-xs text-text-muted font-light">{timeAgo(agent.updated_at)}</span>
              </div>
            ))}
          </Card>
        )
      ) : (
        <Card className="p-12 text-center">
          <p className="text-sm text-text-muted mb-4">
            {search ? 'No agents match your search.' : 'No agents yet. Create one to get started.'}
          </p>
          {!search && <Button onClick={() => navigate('/agents/new')}>Create your first agent</Button>}
        </Card>
      )}
    </div>
  );
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
