import { useCallback, useEffect, useId, useRef, type RefObject } from 'react';
import { useApi } from '../api/ApiProvider.tsx';
import { HOME } from '../app/destinations.ts';
import { Link } from '../app/router.tsx';
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
 * Answers that override retention (fail closed): a denial, a backend that publishes no descriptor and
 * a descriptor this frontend does not support (or an answer that is no descriptor at all) replace shown content at once and invalidate every
 * check issued before them, so a "Compatible" verdict never outlives a backend rollback or a
 * permission change. Only a check sent afterwards can bring content back.
 */
function invalidatesView(next: Probe): boolean {
  if (next.kind === 'denied' || next.kind === 'not-found' || isNotADescriptor(next)) return true;
  return next.kind === 'ok' && evaluateCompatibility(next.value.apiContract).verdict !== 'compatible';
}

/**
 * A successful (2xx) answer that is not a descriptor: usually the API path is routed to something
 * other than the backend. The pair cannot be verified, so it is treated like a missing descriptor.
 */
function isNotADescriptor(probe: Probe): boolean {
  return probe.kind === 'error' && probe.status !== undefined && probe.status >= 200 && probe.status < 300;
}

/**
 * Only descriptors and a denial are held against later answers. An error, an offline answer or a
 * missing descriptor is not content: the next different answer replaces it without "New updates".
 */
function retainsView(shown: Probe): boolean {
  return shown.kind === 'ok' || shown.kind === 'denied';
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/**
 * Workspace connection (AC3/AC4): checks the backend's published API contract against the contract
 * this frontend supports, and renders every state distinctly: loading, offline (nothing new is
 * fetched or shown), denied (content removed, neutral copy, a return link), unsupported (incompatible
 * pair or no descriptor), error, and compatible. A changed descriptor waits behind "New updates";
 * answers that fail closed apply at once.
 *
 * Focus: a denial moves focus to its neutral heading when it appears, on first paint and from a
 * background check alike (OM-01.04 matrix row "Denied": the content the person was reading is gone),
 * and the state message's polite live region announces it as well. A denial that is already shown
 * does not take focus again on the next check. While a modal dialog is open the page behind it is
 * inert and cannot take focus, so the move waits until the dialog has closed. No other background change takes focus: it moves
 * only to repair it, to this panel's heading, when the change removed the control that held it.
 */
export function ConnectionPanel({ pollIntervalMs = CONNECTION_POLL_MS }: { pollIntervalMs?: number }) {
  const api = useApi();
  const online = useOnline();
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const lastFocusedRef = useRef<Element | null>(null);
  const deniedTitleRef = useRef<HTMLElement | null>(null);
  const deniedShownRef = useRef(false);
  const deniedFocusWaitsRef = useRef(false);

  const load = useCallback(() => api.get(DESCRIPTOR_PATH, { protected: false }, parseDescriptor), [api]);
  const resource = useRevalidatingResource<Probe>({
    load,
    intervalMs: pollIntervalMs,
    isEqual: probesEqual,
    enabled: online,
    invalidates: invalidatesView,
    retains: retainsView,
  });

  // Remembers the element inside this panel that last held focus (native listeners: the section
  // itself is not an interactive element). Focus that moves to an element outside the panel forgets it.
  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return undefined;
    const onFocusIn = (event: FocusEvent) => {
      lastFocusedRef.current = event.target instanceof Element ? event.target : null;
    };
    const onFocusOut = (event: FocusEvent) => {
      if (event.relatedTarget instanceof Node) {
        if (!section.contains(event.relatedTarget)) lastFocusedRef.current = null;
        return;
      }
      // No destination has two causes. The focused control is being removed (Chromium reports it this
      // way while the control is still connected): kept, that is the case the repair below is for.
      // Or the person left it, for example by clicking page text, so focus fell to the document:
      // forgotten, or a later background change would move focus without a user action. The two are
      // told apart once the event has finished: a control that was left is still in the document and
      // no longer focused (a window that lost focus keeps it as the active element).
      const left = event.target;
      queueMicrotask(() => {
        if (lastFocusedRef.current === left && left instanceof Element && left.isConnected && document.activeElement !== left) {
          lastFocusedRef.current = null;
        }
      });
    };
    section.addEventListener('focusin', onFocusIn);
    section.addEventListener('focusout', onFocusOut);
    return () => {
      section.removeEventListener('focusin', onFocusIn);
      section.removeEventListener('focusout', onFocusOut);
    };
  }, []);

  const probe = resource.current;
  const denied = probe?.kind === 'denied';
  const pendingCount = resource.pendingCount;
  useEffect(() => {
    // A denial that has just appeared takes focus to its neutral heading, wherever focus was. Only
    // the transition does: the same denial confirmed by a later check leaves focus alone.
    const appeared = denied && !deniedShownRef.current;
    deniedShownRef.current = denied;
    if (!denied) deniedFocusWaitsRef.current = false;
    if (appeared) {
      lastFocusedRef.current = null;
      const title = deniedTitleRef.current;
      title?.focus();
      // An open modal dialog makes everything behind it inert, so the heading could not take focus
      // (and must not: focus stays in the dialog). The move is owed until the dialog has closed.
      deniedFocusWaitsRef.current = title !== null && document.activeElement !== title && document.querySelector('dialog[open]') !== null;
      return;
    }
    // Every other change repairs only: the control that held focus (the "Show update" button, the
    // return link) was removed by a change of the shown answer and focus fell back to the document.
    // It goes to this panel's heading. Focus anywhere else is left alone.
    const last = lastFocusedRef.current;
    if (last === null || last.isConnected) return;
    lastFocusedRef.current = null;
    const active = document.activeElement;
    if (active !== null && active !== document.body) return;
    headingRef.current?.focus();
  }, [probe, denied, pendingCount]);
  useEffect(() => {
    if (!denied) return undefined;
    // The owed move. `close` does not bubble, so it is caught on the way down. The dialog's own
    // close handler runs after this one and returns focus to the control that opened it; the
    // heading takes focus in the next task, once that has happened.
    let timer: number | undefined;
    const onDialogClose = () => {
      if (!deniedFocusWaitsRef.current) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (!deniedFocusWaitsRef.current || document.querySelector('dialog[open]') !== null) return;
        deniedFocusWaitsRef.current = false;
        deniedTitleRef.current?.focus();
      }, 0);
    };
    document.addEventListener('close', onDialogClose, true);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('close', onDialogClose, true);
    };
  }, [denied]);
  const checkedAt = resource.receivedAt ? `Checked at ${formatTime(resource.receivedAt)} (browser time).` : '';

  return (
    <section className="panel" aria-labelledby={headingId} ref={sectionRef}>
      <h2 id={headingId} ref={headingRef} tabIndex={-1}>
        Workspace connection
      </h2>
      {!online ? (
        <StateMessage kind="offline" title="You are offline">
          <p>
            Nothing new is requested or shown while offline. {probe?.kind === 'ok' ? 'The values below are from the last check and may be stale.' : ''}{' '}
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
      {probe ? <ProbeView probe={probe} stale={!online || resource.stale} online={online} deniedTitleRef={deniedTitleRef} /> : null}
      {checkedAt ? <p className="meta">{checkedAt}</p> : null}
      <NewUpdates count={resource.pendingCount} onApply={resource.applyPending} focusTarget={() => headingRef.current} />
    </section>
  );
}

interface ProbeViewProps {
  probe: Probe;
  stale: boolean;
  online: boolean;
  deniedTitleRef: RefObject<HTMLElement | null>;
}

function ProbeView({ probe, stale, online, deniedTitleRef }: ProbeViewProps) {
  switch (probe.kind) {
    case 'offline':
      // The request failed because the connection dropped before the browser reported it. The
      // panel-level offline message covers the reported case; this one covers the gap.
      return online ? (
        <StateMessage kind="offline" title="The connection dropped during the check" as="h3">
          <p>Nothing was received, so nothing is shown. The backend is checked again automatically.</p>
        </StateMessage>
      ) : null;
    case 'denied':
      return (
        <StateMessage
          kind="denied"
          title="This connection isn't available to this session"
          as="h3"
          titleRef={deniedTitleRef}
          action={
            <Link to={HOME.path} className="action action--secondary">
              Return to {HOME.label}
            </Link>
          }
        >
          <p>Access could not be confirmed, so nothing from the backend is shown.</p>
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
      if (isNotADescriptor(probe)) {
        // "Status 200" would read as healthy, so it is never shown.
        return (
          <StateMessage kind="unsupported" title="The answer was not a compatibility descriptor" as="h3">
            <p>
              Something answered <code>{DESCRIPTOR_PATH}</code> under the API path, but not with the backend&apos;s descriptor, so
              the frontend/backend pair cannot be verified and is treated as unsupported. Check that the API path is routed to
              the backend.
            </p>
          </StateMessage>
        );
      }
      return (
        <StateMessage kind="error" title="The backend could not be reached" as="h3">
          <p>
            {probe.status ? `The backend answered with status ${probe.status}.` : 'No answer was received.'} Nothing shown here is
            new; the check repeats automatically.
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
              <p>{verdict.reason} Deploy a supported pair before relying on this workspace.</p>
            </StateMessage>
          )}
        </>
      );
    }
  }
}
