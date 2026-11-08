import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Link, RouterProvider, normalizePath, useRouter } from './router.tsx';

function Probe() {
  const router = useRouter();
  return (
    <div>
      <output data-testid="path">{router.pathname}</output>
      <output data-testid="count">{router.navigationCount}</output>
      <output data-testid="depth">{router.depth}</output>
      <Link to="/focus">Focus</Link>
      <button
        type="button"
        onClick={() => {
          router.returnTo('/');
        }}
      >
        return
      </button>
    </div>
  );
}

describe('router', () => {
  it('normalises trailing slashes', () => {
    expect(normalizePath('/focus/')).toBe('/focus');
    expect(normalizePath('/')).toBe('/');
    expect(normalizePath('')).toBe('/');
  });

  it('starts at the current location with no in-app navigation recorded', () => {
    window.history.replaceState(null, '', '/knowledge');
    render(
      <RouterProvider>
        <Probe />
      </RouterProvider>,
    );
    expect(screen.getByTestId('path')).toHaveTextContent('/knowledge');
    expect(screen.getByTestId('count')).toHaveTextContent('0');
    expect(screen.getByTestId('depth')).toHaveTextContent('0');
  });

  it('navigates on a plain click, records depth, and returns to the fallback when there is no in-app history', async () => {
    window.history.replaceState(null, '', '/');
    const user = userEvent.setup();
    render(
      <RouterProvider>
        <Probe />
      </RouterProvider>,
    );
    await user.click(screen.getByRole('link', { name: 'Focus' }));
    expect(window.location.pathname).toBe('/focus');
    expect(screen.getByTestId('count')).toHaveTextContent('1');
    expect(screen.getByTestId('depth')).toHaveTextContent('1');

    act(() => {
      window.history.replaceState(null, '', '/usage');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(screen.getByTestId('path')).toHaveTextContent('/usage');
    expect(screen.getByTestId('depth')).toHaveTextContent('0');
    await user.click(screen.getByRole('button', { name: 'return' }));
    expect(window.location.pathname).toBe('/');
    expect(screen.getByTestId('path')).toHaveTextContent('/');
  });

  it('leaves modified clicks to the browser', async () => {
    window.history.replaceState(null, '', '/');
    const user = userEvent.setup();
    render(
      <RouterProvider>
        <Probe />
      </RouterProvider>,
    );
    await user.keyboard('{Control>}');
    await user.click(screen.getByRole('link', { name: 'Focus' }));
    await user.keyboard('{/Control}');
    expect(screen.getByTestId('count')).toHaveTextContent('0');
  });
});
