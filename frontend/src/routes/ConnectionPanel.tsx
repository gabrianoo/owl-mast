import { useCallback, useId, useRef } from 'react';
import { useApi } from '../api/ApiProvider.tsx';
import type { ApiResult } from '../api/client.ts';
import {
  DESCRIPTOR_PATH,
  FRONTEND_VERSION,
  SUPPORTED_CONTRACT,
  descriptorsEqual,
  evaluateCompatibility,
  formatContract,
  parseDescriptor,
  type CompatibilityDescriptor,
} from '../api/compatibility.ts';
import { NewUpdates } from '../primitives/NewUpdates.tsx';
import { StateMessage } from '../primitives/StateMessage.tsx';
import { useRevalidatingResource } from '../primitives/useRevalidatingResource.ts';
import { useOnline } from '../state/connectivity.tsx';

export const CONNECTION_POLL_MS = 30_000;

type Probe = ApiResult<CompatibilityDescriptor>;

function probesEqual(a: Probe, b: Probe): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === 'ok' && b.kind === 'ok') return descriptorsEqual(a.value, b.value);
  if (a.kind === 'error' && b.kind === 'error') return a.status === b.status;
  return true;
}

/**
 * Permission or scope removal overrides retention: a denied answer replaces shown content at once and
 * invalidates every check issued before it, so only a check sent afterwards can bring content back.
 */
function invalidatesView(next: Probe): boolean {
  return next.kind === 'denied';
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/**
 * Workspace connection (AC3/AC4): checks the backend's published API contract against the contract
 * this frontend supports, and renders every state distinctly: loading, offline (nothing new is
 * fetched or shown), denied (content removed, neutral copy, focus moved), unsupported (incompatible
 * pair or no descriptor), error, and compatible. Re-checks wait behind "New updates".
 */
export function ConnectionPanel({ pollIntervalMs = CONNECTION_POLL_MS }: { pollIntervalMs?: number }) {
  const api = useApi();
  const online = useOnline();
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement | null>(null);

  const load = useCallback(() => api.get(DESCRIPTOR_PATH, { protected: false }, parseDescriptor), [api]);
  const resource = useRevalidatingResource<Probe>({
    load,
    intervalMs: pollIntervalMs,
    isEqual: probesEqual,
    enabled: online,
    invalidates: invalidatesView,
  });

  const probe = resource.current;
  const checkedAt = resource.receivedAt ? `Checked at ${formatTime(resource.receivedAt)} (browser time).` : '';

  return (
    <section className="panel" aria-labelledby={headingId}>
      <h2 id={headingId} ref={headingRef} tabIndex={-1}>
        Workspace connection
      </h2>
      {!online ? (
        <StateMessage kind="offline" title="You are offline">
          <p>
            Nothing new is requested or shown while offline. {probe ? 'The values below are from the last check and may be stale.' : ''}{' '}
            Access is checked again when the connection returns.
          </p>
        </StateMessage>
      ) : null}
      {online && resource.loading ? (
        <StateMessage kind="loading" title="Checking the backend connection">
          <p>Waiting for the backend to publish its API contract. No values are shown until it answers.</p>
        </StateMessage>
      ) : null}
      {/* Values from before the connection was lost stay labelled stale until a post-reconnect check
          confirms or replaces them. */}
      {probe ? <ProbeView probe={probe} stale={!online || resource.stale} /> : null}
      {checkedAt ? <p className="meta">{checkedAt}</p> : null}
      <NewUpdates count={resource.pendingCount} onApply={resource.applyPending} focusTarget={() => headingRef.current} />
    </section>
  );
}

function ProbeView({ probe, stale }: { probe: Probe; stale: boolean }) {
  switch (probe.kind) {
    case 'offline':
      return null;
    case 'denied':
      return (
        <StateMessage kind="denied" title="This connection isn't available to this session" focusOnMount as="h3">
          <p>Access could not be confirmed, so nothing from the backend is shown. Return to your work.</p>
        </StateMessage>
      );
    case 'not-found':
      return (
        <StateMessage kind="unsupported" title="The backend did not publish a compatibility descriptor" as="h3">
          <p>
            The frontend/backend pair cannot be verified, so it is treated as unsupported. The backend must answer{' '}
            <code>{DESCRIPTOR_PATH}</code> under the API path.
          </p>
        </StateMessage>
      );
    case 'error':
      return (
        <StateMessage kind="error" title="The backend could not be reached" as="h3">
          <p>
            {probe.status ? `The backend answered with status ${probe.status}.` : 'No answer was received.'} Nothing shown here is
            new; try again later.
          </p>
        </StateMessage>
      );
    case 'ok': {
      const verdict = evaluateCompatibility(probe.value.apiContract);
      return (
        <>
          <dl className="facts">
            <dt>Backend service</dt>
            <dd>{probe.value.service}</dd>
            <dt>Backend version</dt>
            <dd>{probe.value.backendVersion}</dd>
            <dt>Backend API contract</dt>
            <dd>{formatContract(probe.value.apiContract)}</dd>
            <dt>Frontend version</dt>
            <dd>{FRONTEND_VERSION}</dd>
            <dt>Frontend supports</dt>
            <dd>
              {SUPPORTED_CONTRACT.major}.x, at least {SUPPORTED_CONTRACT.major}.{SUPPORTED_CONTRACT.minMinor}
            </dd>
          </dl>
          {stale ? (
            <StateMessage kind="stale" title="Last known values" as="h3">
              <p>These values were received before the connection was lost and have not been re-checked.</p>
            </StateMessage>
          ) : verdict.verdict === 'compatible' ? (
            <StateMessage kind="ready" title="Compatible frontend and backend" as="h3">
              <p>The backend publishes API contract {formatContract(verdict.backend)}, which this frontend supports.</p>
            </StateMessage>
          ) : (
            <StateMessage kind="unsupported" title="Incompatible frontend and backend" as="h3">
              <p>{verdict.reason} Protected features stay unavailable until a supported pair is deployed.</p>
            </StateMessage>
          )}
        </>
      );
    }
  }
}
