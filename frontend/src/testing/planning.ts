import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

/** The frontend package root: the nearest ancestor of the working directory holding this package.json. */
function frontendRoot(): string {
  let dir = process.cwd();
  for (;;) {
    const candidate = resolve(dir, 'package.json');
    if (existsSync(candidate) && readFileSync(candidate, 'utf8').includes('"owl-mast-frontend"')) return dir;
    const parent = dirname(dir);
    if (parent === dir) throw new Error('frontend package root not found from ' + process.cwd());
    dir = parent;
  }
}

const FRONTEND_ROOT = frontendRoot();

/** Planning artifacts the shell must preserve; tests read them from the repository directly. */
export const UX_DIR = resolve(FRONTEND_ROOT, '../_bmad-output/planning-artifacts/ux-designs/ux-owl-mast-2026-11-05');

export function readPlanningFile(relativePath: string): string {
  return readFileSync(resolve(UX_DIR, relativePath), 'utf8');
}

export function readFrontendFile(relativePath: string): string {
  return readFileSync(resolve(FRONTEND_ROOT, relativePath), 'utf8');
}

export interface DesignTokens {
  colors: Record<string, string>;
  typography: Record<string, Record<string, string>>;
  rounded: Record<string, string>;
  spacing: Record<string, string>;
}

/** Parses the DESIGN.md frontmatter sections the shell depends on (flat maps plus flow maps). */
export function parseDesignTokens(markdown: string): DesignTokens {
  const frontmatter = markdown.split('\n---\n')[0] ?? '';
  const lines = frontmatter.split('\n');
  const result: DesignTokens = { colors: {}, typography: {}, rounded: {}, spacing: {} };
  let section: keyof DesignTokens | null = null;
  for (const line of lines) {
    const top = /^([a-z-]+):\s*$/.exec(line);
    if (top) {
      section = (['colors', 'typography', 'rounded', 'spacing'] as const).find((name) => name === top[1]) ?? null;
      continue;
    }
    if (!section || !line.startsWith('  ')) continue;
    const entry = /^ {2}'?([A-Za-z0-9-]+)'?:\s*(.+)$/.exec(line);
    if (!entry) continue;
    const [, key, rawValue] = entry;
    if (!key || rawValue === undefined) continue;
    if (section === 'typography') {
      result.typography[key] = parseFlowMap(rawValue);
    } else {
      result[section][key] = unquote(rawValue.trim());
    }
  }
  return result;
}

function parseFlowMap(raw: string): Record<string, string> {
  const inner = raw.trim().replace(/^\{/, '').replace(/\}$/, '');
  const map: Record<string, string> = {};
  let current = '';
  let quote: string | null = null;
  const parts: string[] = [];
  for (const char of inner) {
    if (quote) {
      current += char;
      if (char === quote) quote = null;
    } else if (char === "'" || char === '"') {
      quote = char;
      current += char;
    } else if (char === ',') {
      parts.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  if (current.trim()) parts.push(current);
  for (const part of parts) {
    const index = part.indexOf(':');
    const key = part.slice(0, index).trim();
    const value = unquote(part.slice(index + 1).trim());
    map[key] = value;
  }
  return map;
}

function unquote(value: string): string {
  return value.replace(/^'(.*)'$/, '$1').replace(/^"(.*)"$/, '$1');
}

/** Reads `--name: value;` declarations from one CSS block selected by its selector text. */
export function cssBlock(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf('{', start);
  let depth = 0;
  let end = open;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    if (css[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  const body = css.slice(open + 1, end);
  const declarations: Record<string, string> = {};
  for (const match of body.matchAll(/(--[a-z0-9-]+|color-scheme):\s*([^;]+);/g)) {
    const [, name, value] = match;
    if (name && value) declarations[name] = value.trim();
  }
  return declarations;
}

/** WCAG 2.x relative luminance and contrast ratio for #RRGGBB colours. */
export function contrastRatio(foreground: string, background: string): number {
  const l1 = luminance(foreground);
  const l2 = luminance(background);
  const [light, dark] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (light + 0.05) / (dark + 0.05);
}

function luminance(hex: string): number {
  const value = hex.replace('#', '');
  const channel = (offset: number) => {
    const c = parseInt(value.slice(offset, offset + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}
