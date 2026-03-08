import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Card } from '../Card';

describe('Card', () => {
  it('renders children', () => {
    render(<Card>Card content</Card>);
    expect(screen.getByText('Card content')).toBeInTheDocument();
  });

  it('applies hoverable class when prop is set', () => {
    const { container } = render(<Card hoverable>Hoverable</Card>);
    expect(container.firstChild).toHaveClass('cursor-pointer');
  });

  it('does not apply hoverable class by default', () => {
    const { container } = render(<Card>Default</Card>);
    expect(container.firstChild).not.toHaveClass('cursor-pointer');
  });
});
