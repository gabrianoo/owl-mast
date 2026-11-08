import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

/**
 * action-control / action-control-dark (UX-DR27): one behaviour in both themes. While the action is
 * pending the control refuses duplicate activation, keeps its readable label and explains why; the
 * result shown afterwards is the actual outcome. A rejected action is never presented as success.
 */
export type ActionOutcome = { ok: true; message: string } | { ok: false; message: string };

export interface ActionButtonProps {
  children: ReactNode;
  onAction: () => Promise<ActionOutcome>;
  variant?: 'primary' | 'secondary';
  pendingLabel?: string;
  type?: 'button' | 'submit';
  describedBy?: string;
}

type Phase = { name: 'idle' } | { name: 'pending' } | { name: 'settled'; outcome: ActionOutcome };

export function ActionButton({
  children,
  onAction,
  variant = 'primary',
  pendingLabel = 'Working… the result appears here when it is known.',
  type = 'button',
  describedBy,
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
      outcome = { ok: false, message: failure instanceof Error && failure.message ? failure.message : 'The action failed.' };
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
        onClick={() => {
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
