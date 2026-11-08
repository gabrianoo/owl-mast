import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BrandMark } from '../app/shell/BrandMark.tsx';
import { readFrontendFile, readPlanningFile } from '../testing/planning.ts';
import { OWL_MARK } from './owlMark.ts';

const accepted = readPlanningFile('assets/owl-mark.svg');

function attribute(svg: string, name: string): string | undefined {
  return new RegExp(`${name}="([^"]+)"`).exec(svg)?.[1];
}

function paths(svg: string): string[] {
  return [...svg.matchAll(/<path d="([^"]+)"\/>/g)].map((match) => match[1] ?? '');
}

describe('AC1 / UX-DR07: the accepted owl mark is preserved', () => {
  it('matches the accepted asset geometry, stroke and currentColor', () => {
    expect(OWL_MARK.viewBox).toBe(attribute(accepted, 'viewBox'));
    expect(OWL_MARK.fill).toBe(attribute(accepted, 'fill'));
    expect(OWL_MARK.stroke).toBe('currentColor');
    expect(OWL_MARK.stroke).toBe(attribute(accepted, 'stroke'));
    expect(OWL_MARK.strokeWidth).toBe(attribute(accepted, 'stroke-width'));
    expect(OWL_MARK.strokeLinecap).toBe(attribute(accepted, 'stroke-linecap'));
    expect(OWL_MARK.strokeLinejoin).toBe(attribute(accepted, 'stroke-linejoin'));
    expect([...OWL_MARK.paths]).toEqual(paths(accepted));
    expect(paths(accepted)).toHaveLength(3);
  });

  it('ships the favicon as a byte-identical copy of the accepted asset', () => {
    expect(readFrontendFile('public/owl-mark.svg')).toBe(accepted);
  });

  it('renders decoratively at 24px with the three accepted paths', () => {
    render(<BrandMark />);
    const svg = screen.getByTestId('brand-mark');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('width', '24');
    expect(svg).toHaveAttribute('height', '24');
    expect(svg).toHaveAttribute('stroke', 'currentColor');
    expect(svg).toHaveAttribute('stroke-width', '1.8');
    expect([...svg.querySelectorAll('path')].map((path) => path.getAttribute('d'))).toEqual(paths(accepted));
  });
});
