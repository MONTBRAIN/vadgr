import { useState, useRef, useEffect } from 'react';
import { Button } from '../ui/Button';
import type { SchemaField } from '../../types';

interface SchemaEditorProps {
  label: string;
  fields: SchemaField[];
  onChange: (fields: SchemaField[]) => void;
  isInput?: boolean;
  readOnly?: boolean;
}

const INPUT_TYPES = ['text', 'url', 'number', 'boolean', 'directory', '.txt', '.csv', '.json', '.xml', '.pdf', '.docx', '.xlsx', '.pptx', '.zip', '.tar.gz', '.png', '.jpg', '.html', '.md', '.yaml', '.sql'];
const OUTPUT_TYPES = ['text', 'url', 'number', 'boolean', 'directory', '.txt', '.csv', '.json', '.xml', '.pdf', '.docx', '.xlsx', '.pptx', '.html', '.md', '.yaml', '.png', '.jpg', '.svg', '.zip'];

function TypeCombobox({
  value,
  types,
  onChange,
  disabled,
}: {
  value: string;
  types: string[];
  onChange: (val: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { setInputValue(value); }, [value]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const isExactMatch = types.includes(inputValue);
  const filtered = isExactMatch ? types : types.filter(t => t.includes(inputValue.toLowerCase()));

  const commit = (val: string) => {
    const trimmed = val.trim();
    if (trimmed) onChange(trimmed);
    setOpen(false);
  };

  return (
    <div className="relative shrink-0" ref={ref}>
      <div className="flex">
        <input
          value={inputValue}
          onChange={(e) => { setInputValue(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => { setTimeout(() => commit(inputValue), 150); }}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(inputValue); } }}
          placeholder="type"
          disabled={disabled}
          className="w-20 px-2 py-1 bg-bg-input border border-border rounded-l-md text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
        />
        <button
          type="button"
          onMouseDown={(e) => { e.preventDefault(); setOpen(!open); }}
          disabled={disabled}
          className="px-1 bg-bg-input border border-l-0 border-border rounded-r-md text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
          title="Show types"
        >
          <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>
      {open && filtered.length > 0 && (
        <div className="absolute z-50 top-full mt-1 left-0 w-32 max-h-48 overflow-y-auto bg-bg-secondary border border-border rounded-md shadow-lg">
          {filtered.map(t => (
            <button
              key={t}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); setInputValue(t); onChange(t); setOpen(false); }}
              className={`w-full text-left px-2.5 py-1.5 text-xs transition-colors cursor-pointer ${
                t === value ? 'text-accent bg-accent/10' : 'text-text-primary hover:bg-hover-bg'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function SchemaEditor({ label, fields, onChange, isInput = true, readOnly = false }: SchemaEditorProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const dragNode = useRef<HTMLDivElement | null>(null);

  const types = isInput ? INPUT_TYPES : OUTPUT_TYPES;

  const addField = () => {
    if (readOnly) return;
    onChange([...fields, { name: '', type: 'text', required: isInput }]);
  };

  const removeField = (index: number) => {
    if (readOnly) return;
    onChange(fields.filter((_, i) => i !== index));
  };

  const updateField = (index: number, patch: Partial<SchemaField>) => {
    if (readOnly) return;
    onChange(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  };

  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDragIndex(index);
    dragNode.current = e.currentTarget as HTMLDivElement;
    e.dataTransfer.effectAllowed = 'move';
    requestAnimationFrame(() => {
      if (dragNode.current) dragNode.current.style.opacity = '0.4';
    });
  };

  const handleDragEnd = () => {
    if (dragNode.current) dragNode.current.style.opacity = '1';
    if (dragIndex !== null && dropTarget !== null && dragIndex !== dropTarget) {
      const reordered = [...fields];
      const [moved] = reordered.splice(dragIndex, 1);
      reordered.splice(dropTarget, 0, moved);
      onChange(reordered);
    }
    setDragIndex(null);
    setDropTarget(null);
    dragNode.current = null;
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDropTarget(index);
  };

  return (
    <div className="space-y-2">
      <label className="block font-body text-[11px] font-semibold text-text-muted uppercase tracking-wider">{label}</label>

      {fields.length === 0 ? (
        <p className="font-body text-xs text-text-muted italic">No fields defined. Forge will generate these automatically.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {fields.map((field, i) => (
            <div
              key={i}
              draggable={!readOnly}
              onDragStart={(e) => handleDragStart(e, i)}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => handleDragOver(e, i)}
              className={`group flex items-center gap-2 px-2 py-1.5 rounded-lg bg-bg-secondary border transition-colors ${
                dropTarget === i && dragIndex !== i
                  ? 'border-accent/60'
                  : 'border-border'
              }`}
            >
              {/* Drag handle */}
              {!readOnly && (
                <div className="cursor-grab active:cursor-grabbing text-text-muted hover:text-text-secondary shrink-0" title="Drag to reorder">
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                    <circle cx="5.5" cy="3.5" r="1.2"/><circle cx="10.5" cy="3.5" r="1.2"/>
                    <circle cx="5.5" cy="8" r="1.2"/><circle cx="10.5" cy="8" r="1.2"/>
                    <circle cx="5.5" cy="12.5" r="1.2"/><circle cx="10.5" cy="12.5" r="1.2"/>
                  </svg>
                </div>
              )}

              {/* Number */}
              <span className="font-mono text-xs text-accent w-4 shrink-0">{i + 1}</span>

              {/* Name */}
              <input
                value={field.name}
                onChange={(e) => updateField(i, { name: e.target.value })}
                placeholder="field_name"
                disabled={readOnly}
                className="flex-1 min-w-0 px-2 py-1 bg-bg-input border border-border rounded-md font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
              />

              {/* Type combobox */}
              <TypeCombobox
                value={field.type}
                types={types}
                onChange={(val) => updateField(i, { type: val as SchemaField['type'] })}
                disabled={readOnly}
              />

              {/* Description */}
              <input
                value={field.description ?? ''}
                onChange={(e) => updateField(i, { description: e.target.value || undefined })}
                placeholder="description"
                disabled={readOnly}
                className="flex-[2] min-w-0 px-2 py-1 bg-bg-input border border-border rounded-md text-xs text-text-primary placeholder:text-text-muted focus:border-accent transition-colors"
              />

              {/* Delete */}
              <button
                type="button"
                onClick={() => removeField(i)}
                className="text-text-muted hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 shrink-0 cursor-pointer"
                disabled={readOnly}
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/>
                </svg>
              </button>
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
