import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { WSEvent } from '../../types';

interface RunLogProps {
  events: WSEvent[];
  outputs: Record<string, unknown>;
}

export function RunLog({ events, outputs }: RunLogProps) {
  const [showRaw, setShowRaw] = useState(false);

  const isRunning = events.some(e => e.type === 'run_started' || e.type === 'agent_started') &&
    !events.some(e => e.type === 'run_completed' || e.type === 'run_failed');

  const hasOutputs = Object.keys(outputs).length > 0;
  const rawResult = typeof outputs.result === 'string' ? outputs.result : null;

  let resultText = rawResult;
  if (rawResult) {
    try {
      const parsed = JSON.parse(rawResult);
      if (typeof parsed === 'object' && parsed !== null) {
        const textFields = Object.values(parsed).filter((v): v is string => typeof v === 'string');
        if (textFields.length > 0) {
          resultText = textFields.join('\n\n');
        }
      }
    } catch {
      // Not JSON, use as-is
    }
  }
  const isError = outputs.is_error === true;
  const cost = typeof outputs.total_cost_usd === 'number' ? outputs.total_cost_usd : null;
  const turns = typeof outputs.num_turns === 'number' ? outputs.num_turns : null;
  const durationMs = typeof outputs.duration_ms === 'number' ? outputs.duration_ms : null;

  return (
    <div className="space-y-3">
      {/* Status indicator while running and no outputs yet */}
      {isRunning && !hasOutputs && (
        <div className="flex items-center gap-2 py-3 pl-1">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-text-muted opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-text-muted"></span>
          </span>
          <span className="text-xs text-text-muted">Running... follow progress in Execution Steps</span>
        </div>
      )}

      {/* Final outputs -- shown when run completes */}
      {hasOutputs && resultText ? (
        <>
          <div className={`bg-bg-primary border rounded-lg p-4 overflow-auto max-h-[500px] ${isError ? 'border-danger/40' : 'border-border'}`}>
            <div className={`text-sm ${isError ? 'text-danger' : 'text-text-primary'} markdown-output`}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({ children }) => <h1 className="text-lg font-heading font-semibold mt-4 mb-2">{children}</h1>,
                  h2: ({ children }) => <h2 className="text-base font-heading font-semibold mt-3 mb-1.5">{children}</h2>,
                  h3: ({ children }) => <h3 className="text-sm font-heading font-semibold mt-2 mb-1">{children}</h3>,
                  p: ({ children }) => <p className="mb-2 leading-relaxed">{children}</p>,
                  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                  ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
                  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-2">
                      <table className="w-full text-xs border-collapse border border-border">{children}</table>
                    </div>
                  ),
                  thead: ({ children }) => <thead className="bg-bg-secondary">{children}</thead>,
                  th: ({ children }) => <th className="border border-border px-2 py-1 text-left font-semibold text-text-primary">{children}</th>,
                  td: ({ children }) => <td className="border border-border px-2 py-1 text-text-secondary">{children}</td>,
                  code: ({ children, className }) => {
                    const isBlock = className?.includes('language-');
                    return isBlock
                      ? <code className="block bg-bg-secondary rounded p-2 my-1 font-mono text-xs overflow-auto">{children}</code>
                      : <code className="bg-bg-secondary rounded px-1 py-0.5 font-mono text-xs">{children}</code>;
                  },
                  hr: () => <hr className="border-border my-3" />,
                }}
              >
                {resultText}
              </ReactMarkdown>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            {turns !== null && <span>{turns} turn{turns !== 1 ? 's' : ''}</span>}
            {durationMs !== null && <span>{(durationMs / 1000).toFixed(1)}s</span>}
            {cost !== null && <span>${cost.toFixed(4)}</span>}
            <button
              type="button"
              className="text-accent hover:underline ml-auto"
              onClick={() => setShowRaw(!showRaw)}
            >
              {showRaw ? 'Hide' : 'Show'} raw output
            </button>
          </div>
          {showRaw && (
            <div className="bg-bg-primary border border-border rounded-lg p-4 font-mono text-xs overflow-auto max-h-[300px]">
              <pre className="text-text-secondary whitespace-pre-wrap">
                {JSON.stringify(outputs, null, 2)}
              </pre>
            </div>
          )}
        </>
      ) : hasOutputs ? (
        <div className="bg-bg-primary border border-border rounded-lg p-4 font-mono text-xs overflow-auto max-h-[500px]">
          <pre className="text-text-primary whitespace-pre-wrap">
            {JSON.stringify(outputs, null, 2)}
          </pre>
        </div>
      ) : (
        <div className="bg-bg-primary border border-border rounded-lg p-4 font-mono text-xs">
          <div className="text-text-muted">No output yet.</div>
        </div>
      )}
    </div>
  );
}
