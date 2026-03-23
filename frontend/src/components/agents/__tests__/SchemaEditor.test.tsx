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

  it('renders each field row with name input', () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByDisplayValue('topic')).toBeInTheDocument();
    expect(screen.getByDisplayValue('depth')).toBeInTheDocument();
  });

  it('renders type values inline', () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByDisplayValue('text')).toBeInTheDocument();
    expect(screen.getByDisplayValue('select')).toBeInTheDocument();
  });

  it('renders description inline', () => {
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={vi.fn()} isInput={true} />);
    expect(screen.getByDisplayValue('The subject')).toBeInTheDocument();
  });
});

describe('SchemaEditor - editing fields', () => {
  it('calls onChange when name is edited', async () => {
    const initialFields: SchemaField[] = [{ name: 'old', type: 'text', required: true }];
    const onChange = vi.fn();
    render(<StatefulSchemaEditor initialFields={initialFields} onChange={onChange} />);

    const nameInput = screen.getByDisplayValue('old');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'new');

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall[0].name).toBe('new');
  });

  it('calls onChange when type is changed via dropdown', async () => {
    const initialFields: SchemaField[] = [{ name: 'topic', type: '.txt', required: true }];
    const onChange = vi.fn();
    render(<StatefulSchemaEditor initialFields={initialFields} onChange={onChange} />);

    // Focus the type input to open the dropdown
    const typeInput = screen.getByDisplayValue('.txt');
    await userEvent.click(typeInput);

    // Click the ".csv" option in the dropdown
    const csvOption = screen.getByText('.csv');
    fireEvent.mouseDown(csvOption);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall[0].type).toBe('.csv');
  });

  it('calls onChange when description is edited', () => {
    const initialFields: SchemaField[] = [{ name: 'topic', type: 'text', required: true, description: 'old desc' }];
    const onChange = vi.fn();
    render(<StatefulSchemaEditor initialFields={initialFields} onChange={onChange} />);

    const descInput = screen.getByDisplayValue('old desc');
    fireEvent.change(descInput, { target: { value: 'new desc' } });

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall[0].description).toBe('new desc');
  });

  it('removes a field when X is clicked', async () => {
    const fields: SchemaField[] = [
      { name: 'a', type: 'text', required: true },
      { name: 'b', type: 'text', required: false },
    ];
    const onChange = vi.fn();
    render(<SchemaEditor label="Input Schema" fields={fields} onChange={onChange} isInput={true} />);

    const removeButtons = screen.getAllByRole('button').filter(
      b => b.querySelector('svg line')
    );
    await userEvent.click(removeButtons[0]);
    expect(onChange).toHaveBeenCalledWith([{ name: 'b', type: 'text', required: false }]);
  });
});

describe('SchemaEditor - type combobox allows custom values', () => {
  it('accepts a custom type value', async () => {
    const initialFields: SchemaField[] = [{ name: 'report', type: 'text', required: false }];
    const onChange = vi.fn();
    render(<StatefulSchemaEditor initialFields={initialFields} onChange={onChange} isInput={false} />);

    const typeInput = screen.getByDisplayValue('text');
    await userEvent.clear(typeInput);
    await userEvent.type(typeInput, 'html{enter}');

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall[0].type).toBe('html');
  });
});
