import { StatusBadge } from '../ui/Badge';

export function RunStatusBadge({ status }: { status: string }) {
  return <StatusBadge status={status} />;
}
