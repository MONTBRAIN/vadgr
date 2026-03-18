import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import type { SchemaField } from '../../../types';
import { SchemaEditor } from '../SchemaEditor';

/** Stateful wrapper so SchemaEditor's controlled inputs update properly in tests */
function StatefulSchemaEditor({
  initialFields,
  onChange,
  isInput = true,
}: {
  initialFields: SchemaField[];
  onChange: (f: SchemaField[]) => void;
  isInput?: boolean;
}) {
  const [fields, setFields] = useState(initialFields);
  return (
    <SchemaEditor
      label="Input Schema"
      fields={fields}
      onChange={(f) => { setFields(f); onChange(f); }}
      isInput={isInput}
    />
  );
}

describe('SchemaEditor - empty state', () => {
  it('shows forge inference message when no fields', () => {
    render(<SchemaEditor label="Input Schema" fields={[]} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByText(/forge will generate these automatically/i)).toBeInTheDocument();
  });

  it('shows Add Input button', () => {
    render(<SchemaEditor label="Input Schema" fields={[]} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByText('+ Add Input')).toBeInTheDocument();
  });

  it('shows Add Output button when isInput=false', () => {
    render(<SchemaEditor label="Output Schema" fields={[]} onChange={vi.fn()} isInput={false} />);
    expect(screen.getByText('+ Add Output')).toBeInTheDocument();
  });
});

describe('SchemaEditor - adding fields', () => {
  it('calls onChange with a new field when Add is clicked', async () => {
    const onChange = vi.fn();
    render(<SchemaEditor label="Input Schema" fields={[]} onChange={onChange} isInput={true} />);
    await userEvent.click(screen.getByText('+ Add Input'));
    expect(onChange).toHaveBeenCalledWith([{ name: '', type: 'text', required: true }]);
  });

  it('new output field has required=false by default', async () => {
    const onChange = vi.fn();
    render(<SchemaEditor label="Output Schema" fields={[]} onChange={onChange} isInput={false} />);
    await userEvent.click(screen.getByText('+ Add Output'));
    expect(onChange).toHaveBeenCalledWith([{ name: '', type: 'text', required: false }]);
  });
});

describe('SchemaEditor - existing fields', () => {
  const fields: SchemaField[] = [
    { name: 'topic', type: 'text', required: true, label: 'Research Topic', description: 'The subject' },
    { name: 'depth', type: 'select', required: false, options: ['quick', 'deep'] },
  ];

  it('renders each field row with name', () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByText('topic')).toBeInTheDocument();
    expect(screen.getByText('depth')).toBeInTheDocument();
  });

  it('shows type badge for each field', () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByText('text')).toBeInTheDocument();
    expect(screen.getByText('select')).toBeInTheDocument();
  });

  it('shows required label on required fields', () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByText('required')).toBeInTheDocument();
  });

  it('expands field detail on row click', async () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    await userEvent.click(screen.getByText('topic'));
    // Expanded detail shows label
    expect(screen.getByDisplayValue('Research Topic')).toBeInTheDocument();
    expect(screen.getByDisplayValue('The subject')).toBeInTheDocument();
  });

  it('shows options input for select type when expanded', async () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    await userEvent.click(screen.getByText('depth'));
    // Options field should be visible
    expect(screen.getByDisplayValue('quick, deep')).toBeInTheDocument();
  });

  it('does NOT show options input for non-select types', async () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    await userEvent.click(screen.getByText('topic'));
    expect(screen.queryByDisplayValue('quick, deep')).not.toBeInTheDocument();
  });
});

describe('SchemaEditor - editing fields', () => {
  it('calls onChange when name is edited', async () => {
    const initialFields: SchemaField[] = [{ name: 'old', type: 'text', required: true }];
    const onChange = vi.fn();
    render(<StatefulSchemaEditor initialFields={initialFields} onChange={onChange} />);

    await userEvent.click(screen.getByText('old'));
    const nameInput = screen.getByDisplayValue('old');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'new');

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall[0].name).toBe('new');
  });

  it('calls onChange when options are edited for select', async () => {
    const initialFields: SchemaField[] = [{ name: 'depth', type: 'select', required: false, options: ['a', 'b'] }];
    const onChange = vi.fn();
    render(<StatefulSchemaEditor initialFields={initialFields} onChange={onChange} />);

    await userEvent.click(screen.getByText('depth'));
    const optionsInput = screen.getByDisplayValue('a, b');
    // Use fireEvent.change to set the full value atomically (avoids controlled-input reset mid-type)
    fireEvent.change(optionsInput, { target: { value: 'quick, standard, deep' } });

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall[0].options).toEqual(['quick', 'standard', 'deep']);
  });

  it('removes a field when X is clicked', async () => {
    const fields: SchemaField[] = [
      { name: 'a', type: 'text', required: true },
      { name: 'b', type: 'text', required: false },
    ];
    const onChange = vi.fn();
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={onChange} isInput={true} />);

    // Click the X on the first row (not expanded, just the remove button)
    const removeButtons = screen.getAllByRole('button').filter(
      b => b.querySelector('svg path[d*="M4 4l8 8"]')
    );
    await userEvent.click(removeButtons[0]);
    expect(onChange).toHaveBeenCalledWith([{ name: 'b', type: 'text', required: false }]);
  });
});

describe('SchemaEditor - output mode type options', () => {
  it('does not show file type for output schema', async () => {
    const onChange = vi.fn();
    const fields: SchemaField[] = [{ name: 'out', type: 'text', required: false }];
    render(<SchemaEditor label="Output Schema" fields={fields} onChange={onChange} isInput={false} />);

    await userEvent.click(screen.getByText('out'));
    const typeSelect = screen.getByDisplayValue('text');
    const options = Array.from(typeSelect.querySelectorAll('option')).map(o => o.value);
    expect(options).toContain('file');
    expect(options).toContain('markdown');
    expect(options).toContain('json');
  });

  it('does not show placeholder field for output schema', async () => {
    const fields: SchemaField[] = [{ name: 'out', type: 'text', required: false }];
    render(<SchemaEditor label="Output Schema" fields={fields} onChange={vi.fn()} isInput={false} />);

    await userEvent.click(screen.getByText('out'));
    expect(screen.queryByPlaceholderText(/e\.g\./i)).not.toBeInTheDocument();
  });
});
