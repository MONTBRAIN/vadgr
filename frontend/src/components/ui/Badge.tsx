import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info';

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: 'bg-bg-tertiary text-text-secondary',
  success: 'bg-accent/15 text-accent',
  warning: 'bg-warning/15 text-warning',
  danger: 'bg-danger/15 text-danger',
  info: 'bg-info/15 text-info',
};

export function Badge({ variant = 'default', children, className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  );
}

const statusVariant: Record<string, BadgeVariant> = {
  creating: 'info',
  ready: 'success',
  error: 'danger',
  queued: 'default',
  running: 'info',
  awaiting_approval: 'warning',
  completed: 'success',
  failed: 'danger',
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={statusVariant[status] ?? 'default'}>{status}</Badge>;
}
