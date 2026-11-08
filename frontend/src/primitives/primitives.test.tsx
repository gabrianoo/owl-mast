import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ActionButton } from './ActionButton.tsx';
import { ExternalLink } from './ExternalLink.tsx';
import { ModalDialog } from './ModalDialog.tsx';
import { NewUpdates } from './NewUpdates.tsx';
import { SettingsField } from './SettingsField.tsx';
import { STATE_KIND_LABEL, StateMessage, type StateKind } from './StateMessage.tsx';
import { useRevalidatingResource } from './useRevalidatingResource.ts';

describe('state-message (UX-DR26)', () => {
  it.each(Object.keys(STATE_KIND_LABEL) as StateKind[])('renders the %s kind as text, politely, with its title', (kind) => {
    render(
      <StateMessage kind={kind} title={`Title for ${kind}`}>
        <p>Explanation</p>
      </StateMessage>,
    );
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('data-kind', kind);
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveTextContent(STATE_KIND_LABEL[kind]);
    expect(region).toHaveTextContent(`Title for ${kind}`);
    expect(region.querySelector('[role="progressbar"]')).toBeNull();
  });

  it('moves focus to a neutral unavailable heading when asked', () => {
    render(<StateMessage kind="denied" title="This item is unavailable." focusOnMount as="h2" />);
    expect(screen.getByRole('heading', { level: 2, name: 'This item is unavailable.' })).toHaveFocus();
  });
});

describe('action-control (UX-DR27)', () => {
  it('refuses duplicate activation while pending and shows only the real outcome', async () => {
    const user = userEvent.setup();
    let resolve: (outcome: { ok: true; message: string }) => void = () => undefined;
    const onAction = vi.fn(
      () =>
        new Promise<{ ok: true; message: string }>((done) => {
          resolve = done;
        }),
    );
    render(<ActionButton onAction={onAction}>Save</ActionButton>);
    const button = screen.getByRole('button', { name: 'Save' });
    await user.click(button);
    await user.click(button);
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent(/Working/);
    expect(screen.getByRole('status')).not.toHaveTextContent(/saved/i);
    await act(async () => {
      resolve({ ok: true, message: 'Saved.' });
      await Promise.resolve();
    });
    expect(screen.getByRole('status')).toHaveTextContent('Saved.');
    expect(screen.getByRole('status')).toHaveAttribute('data-outcome', 'succeeded');
    expect(button).not.toHaveAttribute('aria-disabled');
  });

  it('reports a rejected action as a failure, never as success', async () => {
    const user = userEvent.setup();
    render(<ActionButton onAction={() => Promise.reject(new Error('Storage unavailable'))}>Save</ActionButton>);
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await vi.waitFor(() => {
      expect(screen.getByRole('status')).toHaveAttribute('data-outcome', 'failed');
    });
    expect(screen.getByRole('status')).toHaveTextContent('Storage unavailable');
  });
});

describe('external-link (UX-DR28)', () => {
  it('names the destination and marks it external as text', () => {
    render(<ExternalLink href="https://example.test/ticket/1">Open ticket PROJ-1 in Jira</ExternalLink>);
    const link = screen.getByRole('link', { name: /Open ticket PROJ-1 in Jira \(external destination\)/ });
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(link.querySelector('svg, img')).toBeNull();
  });
});

describe('settings-field (UX-DR25)', () => {
  it('keeps label, description and validation visible around the control', () => {
    render(
      <SettingsField id="alias" label="Alias" description="Shown only to you." validation="Alias must be 1–32 characters.">
        <input id="alias" />
      </SettingsField>,
    );
    const input = screen.getByLabelText('Alias');
    expect(screen.getByText('Shown only to you.')).toBeVisible();
    expect(screen.getByText('Alias must be 1–32 characters.')).toBeVisible();
    expect(input).toBeInTheDocument();
  });

  it('renders a grouped control as a fieldset with a legend', () => {
    render(
      <SettingsField id="theme" group label="Theme" description="Pick one.">
        <input type="radio" name="t" aria-label="Light" />
      </SettingsField>,
    );
    expect(screen.getByRole('group', { name: 'Theme' })).toBeInTheDocument();
  });
});

describe('modal dialog (UX-DR40)', () => {
  function Host() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button
          type="button"
          onClick={() => {
            setOpen(true);
          }}
        >
          Open
        </button>
        <ModalDialog
          open={open}
          title="Choose a project"
          onClose={() => {
            setOpen(false);
          }}
        >
          <p>Body</p>
        </ModalDialog>
      </>
    );
  }

  it('opens as a labelled modal, focuses inside, and returns focus to the trigger on close', async () => {
    const user = userEvent.setup();
    render(<Host />);
    const trigger = screen.getByRole('button', { name: 'Open' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Choose a project' });
    expect(dialog).toHaveAttribute('open');
    expect(screen.getByRole('heading', { name: 'Choose a project' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(dialog).not.toHaveAttribute('open');
    expect(trigger).toHaveFocus();
  });

  it('closes on cancel (Escape) and restores focus', async () => {
    const user = userEvent.setup();
    render(<Host />);
    const trigger = screen.getByRole('button', { name: 'Open' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog');
    act(() => {
      dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
    });
    expect(dialog).not.toHaveAttribute('open');
    expect(trigger).toHaveFocus();
  });
});

describe('new updates primitive (UX-DR40, accessibility floor)', () => {
  function Host({ load, isEqual }: { load: () => Promise<number>; isEqual?: (a: number, b: number) => boolean }) {
    const resource = useRevalidatingResource<number>({ load, intervalMs: 1000, isEqual: isEqual ?? ((a, b) => a === b) });
    return (
      <div>
        <h2 id="target" tabIndex={-1}>
          Value {resource.current ?? '…'}
        </h2>
        <NewUpdates count={resource.pendingCount} onApply={resource.applyPending} focusTarget={() => document.getElementById('target')} />
      </div>
    );
  }

  it('holds changed values behind one polite announcement until applied, then focuses the changed section', async () => {
    vi.useFakeTimers();
    try {
      let value = 1;
      const load = vi.fn(() => Promise.resolve(value));
      render(<Host load={load} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByRole('heading')).toHaveTextContent('Value 1');
      value = 2;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByRole('heading')).toHaveTextContent('Value 1');
      expect(screen.getByRole('status')).toHaveTextContent('1 new update available');
      value = 3;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByRole('status')).toHaveTextContent('1 new update available');
      expect(screen.getByRole('heading')).toHaveTextContent('Value 1');
      await act(async () => {
        screen.getByRole('button', { name: 'Show 1 new update' }).click();
        await vi.advanceTimersByTimeAsync(50);
      });
      expect(screen.getByRole('heading')).toHaveTextContent('Value 3');
      expect(screen.getByRole('status')).toHaveTextContent('');
      expect(screen.getByRole('heading')).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it('announces nothing when a re-check returns the same value', async () => {
    vi.useFakeTimers();
    try {
      const load = vi.fn(() => Promise.resolve(7));
      render(<Host load={load} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2500);
      });
      expect(load).toHaveBeenCalledTimes(3);
      expect(screen.getByRole('status')).toHaveTextContent('');
      expect(screen.queryByRole('button')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
