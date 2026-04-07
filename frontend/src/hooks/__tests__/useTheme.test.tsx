import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ThemeProvider, useTheme } from '../useTheme';

function TestConsumer() {
  const { theme, toggle } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={toggle}>toggle</button>
    </div>
  );
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('light');
  });

  it('defaults to dark theme', () => {
    render(<ThemeProvider><TestConsumer /></ThemeProvider>);
    expect(screen.getByTestId('theme').textContent).toBe('dark');
  });

  it('toggles to light and adds class', () => {
    render(<ThemeProvider><TestConsumer /></ThemeProvider>);
    fireEvent.click(screen.getByText('toggle'));
    expect(screen.getByTestId('theme').textContent).toBe('light');
    expect(document.documentElement.classList.contains('light')).toBe(true);
  });

  it('toggles back to dark and removes class', () => {
    render(<ThemeProvider><TestConsumer /></ThemeProvider>);
    fireEvent.click(screen.getByText('toggle'));
    fireEvent.click(screen.getByText('toggle'));
    expect(screen.getByTestId('theme').textContent).toBe('dark');
    expect(document.documentElement.classList.contains('light')).toBe(false);
  });

  it('persists theme to localStorage', () => {
    render(<ThemeProvider><TestConsumer /></ThemeProvider>);
    fireEvent.click(screen.getByText('toggle'));
    expect(localStorage.getItem('vadgr-theme')).toBe('light');
  });

  it('reads stored theme from localStorage', () => {
    localStorage.setItem('vadgr-theme', 'light');
    render(<ThemeProvider><TestConsumer /></ThemeProvider>);
    expect(screen.getByTestId('theme').textContent).toBe('light');
  });
});
