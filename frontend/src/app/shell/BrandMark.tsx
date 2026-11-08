import { OWL_MARK, OWL_MARK_SIZE_PX } from '../../design/owlMark.ts';

/**
 * brand-mark (UX-DR07): the accepted owl SVG with the theme's primary stroke, decorative beside the
 * visible "Owl Mast" text (hidden from assistive technology so the name is not announced twice).
 */
export function BrandMark() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={OWL_MARK_SIZE_PX}
      height={OWL_MARK_SIZE_PX}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={OWL_MARK.viewBox}
      fill={OWL_MARK.fill}
      stroke={OWL_MARK.stroke}
      strokeWidth={OWL_MARK.strokeWidth}
      strokeLinecap={OWL_MARK.strokeLinecap}
      strokeLinejoin={OWL_MARK.strokeLinejoin}
      data-testid="brand-mark"
    >
      {OWL_MARK.paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
