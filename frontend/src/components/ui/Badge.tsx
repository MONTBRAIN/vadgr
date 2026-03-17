import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info';

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: 'text-text-muted',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
  info: 'text-info',
};

export function Badge({ variant = 'default', children, className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  );
}

const statusVariant: Record<string, BadgeVariant> = {
  creating: 'warning',
  updating: 'warning',
  importing: 'warning',
  ready: 'success',
  error: 'danger',
  queued: 'default',
  running: 'info',
  awaiting_approval: 'warning',
  completed: 'success',
  failed: 'danger',
};

const statusColors: Record<string, string> = {
  creating: 'bg-warning',
  updating: 'bg-warning',
  importing: 'bg-warning',
  ready: 'bg-success',
  error: 'bg-danger',
  queued: 'bg-text-muted',
  running: 'bg-info',
  awaiting_approval: 'bg-warning',
  completed: 'bg-success',
  failed: 'bg-danger',
};

export function StatusBadge({ status }: { status: string }) {
  const variant = statusVariant[status] ?? 'default';
  const dotColor = statusColors[status] ?? 'bg-text-muted';
  const isRunning = status === 'running';
  const label = status === 'awaiting_approval' ? 'Awaiting Approval' : status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <Badge variant={variant}>
      <span className={`w-[7px] h-[7px] rounded-full ${dotColor} inline-block shrink-0 ${isRunning ? 'animate-pulse' : ''}`} />
      {label}
    </Badge>
  );
}
