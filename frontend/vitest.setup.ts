import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom has no layout engine and does not implement the <dialog> modal API or matchMedia.
// Provide minimal, behaviour-preserving shims so component tests can exercise the primitives;
// the real browser behaviour is covered by the Playwright suite. Tests that opt into the node
// environment (`@vitest-environment node`) have no DOM, so the shims and cleanup are skipped there.
const hasDom = typeof window !== 'undefined';

beforeEach(() => {
  if (!hasDom) return;
  if (!window.matchMedia) {
    window.matchMedia = (query: string): MediaQueryList =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
  }
  if (!HTMLDialogElement.prototype.showModal || !('__owlmastShim' in HTMLDialogElement.prototype)) {
    Object.defineProperty(HTMLDialogElement.prototype, '__owlmastShim', { value: true, configurable: true });
    HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.show = function show(this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement, returnValue?: string) {
      if (returnValue !== undefined) this.returnValue = returnValue;
      this.removeAttribute('open');
      this.dispatchEvent(new Event('close'));
    };
  }
});

afterEach(() => {
  if (!hasDom) return;
  cleanup();
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-owl-theme');
  document.title = '';
});
