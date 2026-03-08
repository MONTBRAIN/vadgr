import type { ReactNode, HTMLAttributes } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  hoverable?: boolean;
}

export function Card({ children, hoverable = false, className = '', ...props }: CardProps) {
  return (
    <div
      className={`bg-bg-secondary border border-border rounded-xl ${hoverable ? 'hover:border-border-hover transition-colors cursor-pointer' : ''} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
