import type { ReactNode } from 'react';
import type { Destination } from '../app/destinations.ts';

/** Page header shared by every destination: the focusable h1 and a short lede. */
export function DestinationPage({ destination, children }: { destination: Destination; children?: ReactNode }) {
  return (
    <>
      <div className="page-header">
        <h1 tabIndex={-1}>{destination.heading}</h1>
        <p className="lede">{destination.lede}</p>
      </div>
      {children}
    </>
  );
}
