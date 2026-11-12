import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ApiClient, ApiResult } from '../../api/client.ts';
import { App } from '../App.tsx';
import { DESTINATIONS } from '../destinations.ts';

const client: ApiClient = {
  get: <T,>() => Promise.resolve({ kind: 'not-found' } as ApiResult<T>),
};

function renderAt(path: string, wide: boolean) {
  window.matchMedia = (query: string) =>
    ({
      matches: query.includes('min-width: 1024px') ? wide : false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
  window.history.replaceState(null, '', path);
  return render(<App config={{ apiPathPrefix: '/api' }} client={client} />);
}

describe('workspace shell (AC2)', () => {
  it('exposes landmarks, a skip link first, the brand home link and every destination with aria-current', () => {
    renderAt('/', true);
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
    const nav = screen.getByRole('navigation', { name: 'Primary navigation' });
    for (const destination of DESTINATIONS) {
      expect(within(nav).getByRole('link', { name: destination.label })).toHaveAttribute('href', destination.path);
    }
    expect(within(nav).getByRole('link', { name: 'Daily Work' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Focus' })).not.toHaveAttribute('aria-current');
    const brand = screen.getByRole('link', { name: 'Owl Mast home' });
    expect(brand).toHaveTextContent('Owl Mast');
    expect(brand.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(document.title).toBe('Daily Work · Owl Mast');
    expect(screen.getByRole('heading', { level: 1 })).not.toHaveFocus();
  });

  it('keeps project, source identity and period visible in the scope bar', () => {
    renderAt('/', true);
    const scope = screen.getByRole('region', { name: 'Viewing scope' });
    expect(within(scope).getByText('Project')).toBeInTheDocument();
    expect(within(scope).getByText('No project selected')).toBeInTheDocument();
    expect(within(scope).getByText('Source identity')).toBeInTheDocument();
    expect(within(scope).getByText('Not confirmed')).toBeInTheDocument();
    expect(within(scope).getByText('Period')).toBeInTheDocument();
    expect(within(scope).getByText(/^Today · /)).toBeInTheDocument();
  });

  it('updates the title, moves aria-current and focuses the h1 on an in-app navigation', async () => {
    const user = userEvent.setup();
    renderAt('/', true);
    await user.click(screen.getByRole('link', { name: 'Focus' }));
    expect(document.title).toBe('Focus · Owl Mast');
    expect(screen.getByRole('heading', { level: 1, name: 'Focus' })).toHaveFocus();
    expect(screen.getByRole('link', { name: 'Focus' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByText('No assigned work to show')).toBeInTheDocument();
    expect(screen.queryByText(/\d+ (tickets|assignments)/)).toBeNull();
  });

  it('skip link moves focus into the main landmark', async () => {
    const user = userEvent.setup();
    renderAt('/', true);
    await user.tab();
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('main')).toHaveFocus();
  });

  it('below 1024px the navigation sits behind a labelled menu naming the current destination', async () => {
    const user = userEvent.setup();
    renderAt('/usage', false);
    const toggle = screen.getByRole('button', { name: /Navigation.*Usage/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link', { name: 'Focus' })).toBeNull();
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(screen.getByRole('link', { name: 'Focus' }));
    expect(screen.getByRole('button', { name: /Navigation.*Focus/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('heading', { level: 1, name: 'Focus' })).toHaveFocus();
  });

  it('closes the compact menu on Escape and returns focus to its toggle', async () => {
    const user = userEvent.setup();
    renderAt('/usage', false);
    const toggle = screen.getByRole('button', { name: /Navigation.*Usage/ });
    await user.click(toggle);
    await user.tab();
    expect(screen.getByRole('link', { name: 'Daily Work' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link', { name: 'Daily Work' })).toBeNull();
    expect(toggle).toHaveFocus();
    expect(window.location.pathname).toBe('/usage');
  });

  it('closes the compact menu on Escape from outside it without taking focus', async () => {
    const user = userEvent.setup();
    renderAt('/usage', false);
    const toggle = screen.getByRole('button', { name: /Navigation.*Usage/ });
    await user.click(toggle);
    const scope = screen.getByRole('button', { name: 'Change scope' });
    scope.focus();
    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(scope).toHaveFocus();
  });

  it('leaves the compact menu open when Escape belongs to an open dialog, a handled key or a composition', async () => {
    const user = userEvent.setup();
    renderAt('/usage', false);
    const toggle = screen.getByRole('button', { name: /Navigation.*Usage/ });
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: 'Change scope' }));
    expect(screen.getByRole('dialog', { name: 'Choose an authorized project' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    const handled = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    handled.preventDefault();
    const composing = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, isComposing: true });
    act(() => {
      document.body.dispatchEvent(handled);
      document.body.dispatchEvent(composing);
    });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes the compact menu when the link of the page already shown is activated', async () => {
    const user = userEvent.setup();
    renderAt('/usage', false);
    const toggle = screen.getByRole('button', { name: /Navigation.*Usage/ });
    await user.click(toggle);
    await user.click(screen.getByRole('link', { name: 'Usage' }));
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link', { name: 'Usage' })).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Usage' })).toHaveFocus();
  });

  it('opens the scope chooser as a modal and returns focus to Change scope', async () => {
    const user = userEvent.setup();
    renderAt('/', true);
    const trigger = screen.getByRole('button', { name: 'Change scope' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Choose an authorized project' });
    expect(within(dialog).getByText('No authorized projects are available in this session')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(dialog).not.toHaveAttribute('open');
    expect(trigger).toHaveFocus();
  });

  it('renders an unknown address as the unsupported destination with neutral copy and a return', async () => {
    const user = userEvent.setup();
    renderAt('/nope/secret-project', true);
    expect(document.title).toBe('This destination isn’t available · Owl Mast');
    expect(screen.getByRole('heading', { level: 1, name: 'This destination isn’t available' })).toBeInTheDocument();
    expect(screen.queryByText(/secret-project/)).toBeNull();
    await user.click(screen.getByRole('link', { name: 'Back to Daily Work' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Daily Work' })).toHaveFocus();
  });

  it('uses in-app history for the return when one exists', async () => {
    const user = userEvent.setup();
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => undefined);
    renderAt('/', true);
    await user.click(screen.getByRole('link', { name: 'Knowledge' }));
    act(() => {
      window.history.pushState({ owlmastDepth: 2 }, '', '/nowhere');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await user.click(await screen.findByRole('button', { name: 'Back to where you were' }));
    expect(back).toHaveBeenCalledTimes(1);
  });
});
