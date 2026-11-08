import { describe, expect, it } from 'vitest';
import { contrastRatio, cssBlock, parseDesignTokens, readFrontendFile, readPlanningFile } from '../testing/planning.ts';

const design = parseDesignTokens(readPlanningFile('DESIGN.md'));
const css = readFrontendFile('src/design/tokens.css');
const light = cssBlock(css, ':root {');
const darkSystem = cssBlock(css, ':root:not([data-owl-theme="light"])');
const darkOverride = cssBlock(css, ':root[data-owl-theme="dark"]');

const TYPOGRAPHY_VARS: Record<string, string> = {
  title: 'title',
  'title-compact': 'title-compact',
  heading: 'heading',
  body: 'body',
  row: 'row',
  label: 'label',
  meta: 'meta',
  identifier: 'identifier',
};

describe('AC1: exact DESIGN.md tokens are preserved in tokens.css', () => {
  it('parsed the DESIGN.md palette (sanity)', () => {
    expect(design.colors.canvas).toBe('#F5F7FB');
    expect(Object.keys(design.colors)).toHaveLength(34);
    expect(Object.keys(design.typography)).toHaveLength(8);
  });

  it('applies every unsuffixed colour in light mode', () => {
    for (const [name, value] of Object.entries(design.colors)) {
      if (name.endsWith('-dark')) continue;
      expect(light[`--owl-${name}`], `--owl-${name}`).toBe(value);
    }
    expect(light['color-scheme']).toBe('light');
  });

  it('applies every -dark counterpart in dark mode, both for the system theme and the explicit override', () => {
    for (const [name, value] of Object.entries(design.colors)) {
      if (!name.endsWith('-dark')) continue;
      const variable = `--owl-${name.slice(0, -'-dark'.length)}`;
      expect(darkSystem[variable], `${variable} (system dark)`).toBe(value);
      expect(darkOverride[variable], `${variable} (override)`).toBe(value);
    }
    expect(darkSystem['color-scheme']).toBe('dark');
    expect(darkOverride['color-scheme']).toBe('dark');
  });

  it('expresses every typography size as the DESIGN px value in rem at the 16px root, with weight and line height', () => {
    for (const [name, variable] of Object.entries(TYPOGRAPHY_VARS)) {
      const spec = design.typography[name];
      expect(spec, name).toBeDefined();
      if (!spec) continue;
      const px = Number.parseFloat(spec.fontSize ?? '');
      const rem = Number.parseFloat(light[`--owl-type-${variable}-size`] ?? '');
      expect(rem * 16, `${name} size`).toBeCloseTo(px, 6);
      expect(light[`--owl-type-${variable}-weight`], `${name} weight`).toBe(spec.fontWeight);
      expect(light[`--owl-type-${variable}-line`], `${name} line height`).toBe(spec.lineHeight);
    }
    expect(light['--owl-type-title-tracking']).toBe(design.typography.title?.letterSpacing);
    expect(light['--owl-font-sans']).toBe(design.typography.body?.fontFamily);
    expect(light['--owl-font-mono']).toBe(design.typography.identifier?.fontFamily);
  });

  it('keeps radii and the spacing scale, including page margins and the 44px control target', () => {
    for (const [name, value] of Object.entries(design.rounded)) {
      expect(light[`--owl-radius-${name}`], `radius ${name}`).toBe(value);
    }
    for (const [name, value] of Object.entries(design.spacing)) {
      const variable = name === 'control-target' ? '--owl-control-target' : `--owl-space-${name}`;
      expect(light[variable], variable).toBe(value);
    }
    expect(light['--owl-control-target']).toBe('44px');
    expect(light['--owl-focus-width']).toBe('3px');
    expect(light['--owl-focus-offset']).toBe('2px');
  });
});

describe('UX-DR04: exact-palette contrast meets WCAG 2.2 targets in both themes', () => {
  const textRoles = ['text', 'secondary-text', 'primary', 'knowledge', 'attention', 'success', 'error'];
  const surfaces = ['canvas', 'card', 'secondary-surface'];

  it.each([
    ['light', light],
    ['dark', darkOverride],
  ])('%s theme: text roles ≥ 4.5:1, control outline ≥ 3:1, on-primary ≥ 4.5:1', (_theme, palette) => {
    const color = (role: string) => palette[`--owl-${role}`] ?? '';
    for (const role of textRoles) {
      for (const surface of surfaces) {
        expect(contrastRatio(color(role), color(surface)), `${role} on ${surface}`).toBeGreaterThanOrEqual(4.5);
      }
    }
    for (const surface of surfaces) {
      expect(contrastRatio(color('control-outline'), color(surface)), `control-outline on ${surface}`).toBeGreaterThanOrEqual(3);
    }
    expect(contrastRatio(color('on-primary'), color('primary'))).toBeGreaterThanOrEqual(4.5);
    for (const identity of ['iris', 'mulberry', 'clay', 'slate']) {
      expect(contrastRatio(color(`identity-${identity}`), color('card'))).toBeGreaterThanOrEqual(3);
      expect(contrastRatio(color(`identity-${identity}`), color('secondary-surface'))).toBeGreaterThanOrEqual(3);
    }
  });

  it('reproduces the primary-fill figures recorded in DESIGN.md (6.22:1 light, 8.70:1 dark)', () => {
    expect(contrastRatio(light['--owl-on-primary'] ?? '', light['--owl-primary'] ?? '')).toBeCloseTo(6.22, 2);
    expect(contrastRatio(darkOverride['--owl-on-primary'] ?? '', darkOverride['--owl-primary'] ?? '')).toBeCloseTo(8.7, 2);
  });
});
