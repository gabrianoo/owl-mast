import type { MouseEvent } from 'react';

/** Skip-to-content route (UX-DR06): first focusable element; moves focus into the main landmark. */
export function SkipLink({ targetId }: { targetId: string }) {
  const activate = (event: MouseEvent<HTMLAnchorElement>) => {
    const target = document.getElementById(targetId);
    if (target) {
      event.preventDefault();
      target.focus();
      if (typeof target.scrollIntoView === 'function') {
        target.scrollIntoView({ block: 'start' });
      }
    }
  };
  return (
    <a className="skip-link" href={`#${targetId}`} onClick={activate}>
      Skip to main content
    </a>
  );
}
