import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

/**
 * action-control / action-control-dark (UX-DR27): one behaviour in both themes. While the action is
 * pending the control refuses duplicate activation, keeps its readable label and explains why; the
 * result shown afterwards is the actual outcome. A rejected action is never presented as success.
 * An action that throws shows fixed safe copy (`failureMessage`), never the thrown text: exception
 * messages can carry internals. Callers that want a specific failure text return `{ ok: false }`.
 */
export const DEFAULT_FAILURE_MESSAGE = 'The action could not be completed.';

export type ActionOutcome = { ok: true; message: string } | { ok: false; message: string };

export interface ActionButtonProps {
  children: ReactNode;
  onAction: () => Promise<ActionOutcome>;
  variant?: 'primary' | 'secondary';
  pendingLabel?: string;
  type?: 'button' | 'submit';
  describedBy?: string;
  /** Safe copy shown when `onAction` throws instead of returning an outcome. */
  failureMessage?: string;
}

type Phase = { name: 'idle' } | { name: 'pending' } | { name: 'settled'; outcome: ActionOutcome };

export function ActionButton({
  children,
  onAction,
  variant = 'primary',
  pendingLabel = 'Working… the result appears here when it is known.',
  type = 'button',
  describedBy,
  failureMessage = DEFAULT_FAILURE_MESSAGE,
}: ActionButtonProps) {
  const [phase, setPhase] = useState<Phase>({ name: 'idle' });
  const resultId = useId();
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const pending = phase.name === 'pending';

  const activate = async () => {
    if (pending) return;
    setPhase({ name: 'pending' });
    let outcome: ActionOutcome;
    try {
      outcome = await onAction();
    } catch (failure) {
      // The thrown value stays out of the page; the console keeps it for whoever debugs the action.
      console.error('ActionButton: the action threw', failure);
      outcome = { ok: false, message: failureMessage };
    }
    if (mounted.current) {
      setPhase({ name: 'settled', outcome });
    }
  };

  const described = [describedBy, resultId].filter(Boolean).join(' ');
  const resultText = phase.name === 'pending' ? pendingLabel : phase.name === 'settled' ? phase.outcome.message : '';
  const outcomeAttr = phase.name === 'settled' ? (phase.outcome.ok ? 'succeeded' : 'failed') : phase.name;

  return (
    <div className="action-group">
      <button
        type={type}
        className={`action action--${variant}`}
        aria-disabled={pending ? 'true' : undefined}
        aria-busy={pending ? 'true' : undefined}
        aria-describedby={described}
        onClick={(event) => {
          if (pending) {
            // aria-disabled keeps the control focusable, so the browser would still submit the form.
            event.preventDefault();
            return;
          }
          void activate();
        }}
      >
        {children}
      </button>
      <p className="action-result" id={resultId} role="status" aria-live="polite" data-outcome={outcomeAttr}>
        {resultText}
      </p>
    </div>
  );
}
