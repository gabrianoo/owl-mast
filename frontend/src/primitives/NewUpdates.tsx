/**
 * "New updates" control: announces a coalesced polite count once and lets the person apply the
 * waiting values when they are ready; activating it moves focus to the changed section.
 */
export interface NewUpdatesProps {
  count: number;
  onApply: () => void;
  /** Element that receives focus after applying (the changed section's heading). */
  focusTarget: () => HTMLElement | null;
}

export function NewUpdates({ count, onApply, focusTarget }: NewUpdatesProps) {
  const label = count === 1 ? '1 new update' : `${count} new updates`;
  return (
    <div className="new-updates">
      <p role="status" aria-live="polite" aria-atomic="true" className="meta">
        {count > 0 ? `${label} available. Values on this page have not changed yet.` : ''}
      </p>
      {count > 0 ? (
        <button
          type="button"
          className="action action--secondary"
          onClick={() => {
            onApply();
            window.requestAnimationFrame(() => focusTarget()?.focus());
          }}
        >
          Show {label}
        </button>
      ) : null}
    </div>
  );
}
