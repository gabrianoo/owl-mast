import type { ReactNode } from 'react';

/**
 * external-link (UX-DR28): an underlined descriptive label plus a text destination indicator.
 * Navigation only; returning from the destination proves nothing about what happened there.
 */
export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className="external-link" href={href} rel="noopener noreferrer external">
      {children}{' '}
      <span className="external-link__indicator">(external destination)</span>
    </a>
  );
}
