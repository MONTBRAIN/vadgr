import { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { usePairing } from '../../hooks/usePairing';
import { buildPairUri } from '../../lib/pairUri';

// The backend refuses pairing (503) when the transport can't advertise a
// reachable host; its message mentions Tailscale. Detect that case so we can
// show a targeted hint rather than a generic error.
function isTransportUnavailable(error: Error | null): boolean {
  if (!error) return false;
  const m = error.message.toLowerCase();
  return m.includes('tailscale') || m.includes('transport');
}

export function PairDeviceCard() {
  const { mint, data, error, isPending, isError } = usePairing();
  const [copied, setCopied] = useState(false);

  const copyToken = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.pairing_token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable -- the token is shown for manual copy anyway */
    }
  };

  return (
    <Card className="px-7 py-6">
      <div className="flex items-center gap-2.5 mb-1">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="var(--color-accent)" strokeWidth="1.3">
          <rect x="3" y="1.5" width="10" height="13" rx="1.5" />
          <line x1="6.5" y1="12.5" x2="9.5" y2="12.5" strokeLinecap="round" />
        </svg>
        <h2 className="font-heading text-lg font-semibold text-text-primary">Mobile Pairing</h2>
      </div>
      <p className="font-body text-xs text-text-muted font-light ml-[26px] mb-5">
        Pair the Vadgr mobile app by scanning a one-time QR code.
      </p>

      {/* Idle / initial */}
      {!data && !isError && (
        <Button onClick={mint} disabled={isPending}>
          {isPending ? 'Generating...' : 'Pair device'}
        </Button>
      )}

      {/* Error */}
      {isError && !data && (
        <div className="flex flex-col gap-3">
          {isTransportUnavailable(error) ? (
            <p className="text-[13px] text-danger font-body" role="alert">
              Tailscale isn&apos;t available &mdash; enable it to pair over your tailnet.
            </p>
          ) : (
            <p className="text-[13px] text-danger font-body" role="alert">
              {error?.message ?? 'Pairing failed.'}
            </p>
          )}
          <div>
            <Button variant="secondary" size="sm" onClick={mint} disabled={isPending}>
              Retry
            </Button>
          </div>
        </div>
      )}

      {/* Success */}
      {data && (
        <div className="flex flex-col gap-4">
          <div className="self-start rounded-xl bg-white p-3">
            <QRCodeSVG value={buildPairUri(data)} size={200} />
          </div>

          <div>
            <div className="text-xs text-text-muted font-body mb-1">Pairing token (manual entry)</div>
            <div className="flex items-center gap-2">
              <code className="font-mono text-xs text-text-primary bg-bg-input rounded-[8px] px-2.5 py-1.5 break-all">
                {data.pairing_token}
              </code>
              <Button variant="ghost" size="sm" onClick={copyToken}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>

          <div className="text-xs text-text-muted font-body">
            <span className="text-text-secondary">{data.machine_name}</span> &middot;{' '}
            {data.host}:{data.port}
          </div>

          <p className="text-xs text-text-muted font-light">
            This token is one-time and short-lived. Scan with the Vadgr mobile app.
          </p>

          <div>
            <Button variant="secondary" size="sm" onClick={mint} disabled={isPending}>
              {isPending ? 'Regenerating...' : 'Regenerate'}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
