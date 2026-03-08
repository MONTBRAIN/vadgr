import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Badge, StatusBadge } from '../Badge';

describe('Badge', () => {
  it('renders children', () => {
    render(<Badge>test</Badge>);
    expect(screen.getByText('test')).toBeInTheDocument();
  });

  it('applies variant class', () => {
    const { container } = render(<Badge variant="success">ok</Badge>);
    expect(container.firstChild).toHaveClass('text-accent');
  });
});

describe('StatusBadge', () => {
  it('renders status text', () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText('completed')).toBeInTheDocument();
  });

  it('maps creating to info variant', () => {
    const { container } = render(<StatusBadge status="creating" />);
    expect(container.firstChild).toHaveClass('text-info');
  });

  it('maps failed to danger variant', () => {
    const { container } = render(<StatusBadge status="failed" />);
    expect(container.firstChild).toHaveClass('text-danger');
  });
});
