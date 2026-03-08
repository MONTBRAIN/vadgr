interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  id?: string;
}

export function Toggle({ label, checked, onChange, id }: ToggleProps) {
  const toggleId = id ?? label.toLowerCase().replace(/\s+/g, '-');
  return (
    <label htmlFor={toggleId} className="flex items-center gap-3 cursor-pointer">
      <div className="relative">
        <input
          type="checkbox"
          id={toggleId}
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only peer"
        />
        <div className="w-10 h-5 bg-bg-tertiary border border-border rounded-full peer-checked:bg-accent/30 peer-checked:border-accent transition-colors" />
        <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-text-muted rounded-full peer-checked:translate-x-5 peer-checked:bg-accent transition-all" />
      </div>
      <span className="text-sm text-text-secondary">{label}</span>
    </label>
  );
}
