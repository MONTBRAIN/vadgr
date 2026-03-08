import { Button } from '../ui/Button';
import type { SchemaField } from '../../types';

interface SchemaEditorProps {
  label: string;
  fields: SchemaField[];
  onChange: (fields: SchemaField[]) => void;
}

export function SchemaEditor({ label, fields, onChange }: SchemaEditorProps) {
  const addField = () => {
    onChange([...fields, { name: '', type: 'text', required: true }]);
  };

  const removeField = (index: number) => {
    onChange(fields.filter((_, i) => i !== index));
  };

  const updateField = (index: number, patch: Partial<SchemaField>) => {
    onChange(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  };

  return (
    <div className="space-y-3">
      <label className="block text-sm text-text-secondary">{label}</label>
      {fields.length > 0 && (
        <div className="space-y-2">
          <div className="grid grid-cols-[1fr_120px_80px_32px] gap-2 text-xs text-text-muted px-1">
            <span>Name</span>
            <span>Type</span>
            <span>Required</span>
            <span />
          </div>
          {fields.map((field, i) => (
            <div key={i} className="grid grid-cols-[1fr_120px_80px_32px] gap-2 items-center">
              <input
                value={field.name}
                onChange={(e) => updateField(i, { name: e.target.value })}
                placeholder="field_name"
                className="px-3 py-1.5 bg-bg-primary border border-border rounded-lg text-sm text-text-primary"
              />
              <select
                value={field.type}
                onChange={(e) => updateField(i, { type: e.target.value })}
                className="px-2 py-1.5 bg-bg-primary border border-border rounded-lg text-sm text-text-primary"
              >
                <option value="text">text</option>
                <option value="number">number</option>
                <option value="boolean">boolean</option>
              </select>
              <label className="flex items-center justify-center">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={(e) => updateField(i, { required: e.target.checked })}
                  className="w-4 h-4 rounded accent-accent"
                />
              </label>
              <button
                type="button"
                onClick={() => removeField(i)}
                className="w-7 h-7 flex items-center justify-center text-text-muted hover:text-danger rounded transition-colors cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
      <Button type="button" variant="ghost" size="sm" onClick={addField}>
        + Add {label.includes('Input') ? 'Input' : 'Output'}
      </Button>
    </div>
  );
}
