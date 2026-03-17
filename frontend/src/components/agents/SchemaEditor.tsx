import { useState } from 'react';
import { Button } from '../ui/Button';
import type { SchemaField } from '../../types';

interface SchemaEditorProps {
  label: string;
  fields: SchemaField[];
  onChange: (fields: SchemaField[]) => void;
  isInput?: boolean;
  readOnly?: boolean;
}

const INPUT_TYPES = ['text', 'url', 'textarea', 'select', 'number', 'boolean', 'file', 'archive', 'directory', 'json'];
const OUTPUT_TYPES = ['text', 'markdown', 'json', 'url', 'number', 'boolean', 'file', 'archive', 'directory'];

export function SchemaEditor({ label, fields, onChange, isInput = true, readOnly = false }: SchemaEditorProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const addField = () => {
    if (readOnly) return;
    const newIndex = fields.length;
    onChange([...fields, { name: '', type: 'text', required: isInput }]);
    setExpandedIndex(newIndex);
  };

  const removeField = (index: number) => {
    if (readOnly) return;
    onChange(fields.filter((_, i) => i !== index));
    if (expandedIndex === index) setExpandedIndex(null);
  };

  const updateField = (index: number, patch: Partial<SchemaField>) => {
    if (readOnly) return;
    onChange(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  };

  const types = isInput ? INPUT_TYPES : OUTPUT_TYPES;

  return (
    <div className="space-y-2">
      <label className="block font-body text-[11px] font-semibold text-text-muted uppercase tracking-wider">{label}</label>

      {fields.length === 0 ? (
        <p className="font-body text-xs text-text-muted italic">No fields defined. Forge will generate these automatically.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {fields.map((field, i) => (
            <div key={i} className="bg-bg-primary border border-border rounded-[10px] overflow-hidden">
              {/* Row header */}
              <div
                className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-hover-bg transition-colors"
                onClick={() => setExpandedIndex(expandedIndex === i ? null : i)}
              >
                <span className="font-mono text-xs text-accent w-4 shrink-0">{i + 1}</span>
                <span className="font-mono text-xs text-text-primary flex-1 truncate">
                  {field.name || <span className="text-text-muted italic">unnamed</span>}
                </span>
                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-badge-bg text-text-muted border border-border/50">{field.type}</span>
                {field.required && (
                  <span className="font-body text-[10px] text-danger">required</span>
                )}
                <svg
                  width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
                  className={`text-text-muted shrink-0 transition-transform ${expandedIndex === i ? 'rotate-180' : ''}`}
                >
                  <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); removeField(i); }}
                  className="text-text-muted hover:text-danger transition-colors cursor-pointer shrink-0"
                  disabled={readOnly}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round"/>
                  </svg>
                </button>
              </div>

              {/* Expanded detail */}
              {expandedIndex === i && (
                <div className="px-4 pb-4 pt-1 border-t border-border grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Name *</label>
                    <input
                      value={field.name}
                      onChange={(e) => updateField(i, { name: e.target.value })}
                      placeholder="snake_case_key"
                      disabled={readOnly}
                      className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                    />
                  </div>
                  <div>
                    <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Type</label>
                    <select
                      value={field.type}
                      onChange={(e) => updateField(i, { type: e.target.value as SchemaField['type'] })}
                      disabled={readOnly}
                      className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] text-xs text-text-primary focus:border-accent transition-colors"
                    >
                      {types.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Label</label>
                    <input
                      value={field.label ?? ''}
                      onChange={(e) => updateField(i, { label: e.target.value || undefined })}
                      placeholder="Human-readable display name"
                      disabled={readOnly}
                      className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Description</label>
                    <input
                      value={field.description ?? ''}
                      onChange={(e) => updateField(i, { description: e.target.value || undefined })}
                      placeholder="One sentence describing this field"
                      disabled={readOnly}
                      className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                    />
                  </div>
                  {isInput && (
                    <div className="col-span-2">
                      <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Placeholder</label>
                      <input
                        value={field.placeholder ?? ''}
                        onChange={(e) => updateField(i, { placeholder: e.target.value || undefined })}
                        placeholder="e.g. AI market trends 2026"
                        disabled={readOnly}
                        className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                      />
                    </div>
                  )}
                  {field.type === 'select' && (
                    <div className="col-span-2">
                      <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Options (comma-separated)</label>
                      <input
                        value={(field.options ?? []).join(', ')}
                        onChange={(e) => updateField(i, { options: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                        placeholder="quick, standard, deep"
                        disabled={readOnly}
                        className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                      />
                    </div>
                  )}
                  {isInput && (field.type === 'file' || field.type === 'archive' || field.type === 'directory') && (
                    <>
                      <div className="col-span-2">
                        <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Accepted Extensions</label>
                        <input
                          value={(field.accept ?? []).join(', ')}
                          onChange={(e) => updateField(i, {
                            accept: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) || undefined,
                          })}
                          placeholder=".docx, .csv, .zip"
                          disabled={readOnly}
                          className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Accepted MIME Types</label>
                        <input
                          value={(field.mime_types ?? []).join(', ')}
                          onChange={(e) => updateField(i, {
                            mime_types: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) || undefined,
                          })}
                          placeholder="text/csv, application/pdf"
                          disabled={readOnly}
                          className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                        />
                      </div>
                      <div>
                        <label className="block font-body text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">Max Size MB</label>
                        <input
                          type="number"
                          min={1}
                          value={field.max_size_mb ?? ''}
                          onChange={(e) => updateField(i, {
                            max_size_mb: e.target.value ? Number(e.target.value) : undefined,
                          })}
                          placeholder="10"
                          disabled={readOnly}
                          className="w-full px-3 py-1.5 bg-bg-input border border-border rounded-[8px] text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
                        />
                      </div>
                    </>
                  )}
                  {isInput && (
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(e) => updateField(i, { required: e.target.checked })}
                        disabled={readOnly}
                        className="w-3.5 h-3.5 rounded accent-accent"
                        id={`required-${i}`}
                      />
                      <label htmlFor={`required-${i}`} className="font-body text-xs text-text-muted cursor-pointer">Required</label>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <Button type="button" variant="ghost" size="sm" onClick={addField} disabled={readOnly}>
        + Add {isInput ? 'Input' : 'Output'}
      </Button>
    </div>
  );
}
