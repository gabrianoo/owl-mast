/**
 * The accepted owl mark (DESIGN.md: preserve the study's 24×24 geometry, unfilled paths, rounded
 * stroke caps/joins and 1.8-unit stroke; use `currentColor` with the theme's primary token). The
 * values below are asserted against `assets/owl-mark.svg` in owlMark.test.ts; do not redraw.
 */
export const OWL_MARK = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: '1.8',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  paths: ['M4 5l3 2 5-1 5 1 3-2-1 11-7 4-7-4z', 'M7 11h3m4 0h3m-6 3 1 1 1-1', 'M12 2v3m0 16v1'],
} as const;

/** Rendered size of `brand-mark` (DESIGN.md components: size 24px). */
export const OWL_MARK_SIZE_PX = 24;
