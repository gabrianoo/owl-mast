import { useEffect, useRef, type ReactNode, type RefObject } from 'react';

/**
 * state-message (UX-DR26): distinct loading / empty / error / offline / denied / stale /
 * unsupported states with a plain title, a scope-safe explanation and a useful next step. The kind
 * is spelled out as text so it never depends on colour. Loading never shows placeholder numbers.
 */
export type StateKind = 'loading' | 'empty' | 'error' | 'offline' | 'denied' | 'stale' | 'unsupported' | 'ready';

export const STATE_KIND_LABEL: Record<StateKind, string> = {
  loading: 'Loading',
  empty: 'Nothing to show',
  error: 'Problem',
  offline: 'Offline',
  denied: 'Unavailable',
  stale: 'Stale',
  unsupported: 'Unsupported',
  ready: 'Ready',
};

export interface StateMessageProps {
  kind: StateKind;
  title: string;
  children?: ReactNode;
  /** Optional next step: a link or action rendered after the explanation. */
  action?: ReactNode;
  /** Moves keyboard focus to the title when the message appears (denied/unavailable destinations). */
  focusOnMount?: boolean;
  /** Heading level for the title; defaults to a paragraph so lists of states do not fight the page outline. */
  as?: 'h2' | 'h3' | 'p';
  id?: string;
  /** Receives the title element and makes it programmatically focusable, for callers that manage focus themselves. */
  titleRef?: RefObject<HTMLElement | null>;
}

export function StateMessage({ kind, title, children, action, focusOnMount = false, as: Title = 'p', id, titleRef: callerTitleRef }: StateMessageProps) {
  const titleRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (focusOnMount) {
      titleRef.current?.focus();
    }
  }, [focusOnMount]);

  return (
    <section className="state-message" data-kind={kind} role="status" aria-live="polite" aria-atomic="true" id={id}>
      <p className="state-message__kind">{STATE_KIND_LABEL[kind]}</p>
      <Title
        className="state-message__title"
        tabIndex={focusOnMount || callerTitleRef ? -1 : undefined}
        ref={(node: HTMLElement | null) => {
          titleRef.current = node;
          if (callerTitleRef) callerTitleRef.current = node;
        }}
      >
        {title}
      </Title>
      {children}
      {action ? <div className="action-group">{action}</div> : null}
    </section>
  );
}
