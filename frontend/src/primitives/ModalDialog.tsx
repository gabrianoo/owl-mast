import { useEffect, useId, useRef, type ReactNode } from 'react';

/**
 * Temporary overlay (UX-DR40): a named modal dialog with focus inside, an inert background and
 * Escape to close; focus returns to the element that opened it. Uses the native <dialog> modal
 * API, which provides the trap and inert background without a second implementation.
 */
export interface ModalDialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  closeLabel?: string;
}

export function ModalDialog({ open, title, onClose, children, closeLabel = 'Close' }: ModalDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    if (open && !dialog.open) {
      openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.querySelector<HTMLElement>('[data-dialog-initial-focus]')?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    const handleClose = () => {
      const opener = openerRef.current;
      openerRef.current = null;
      onClose();
      if (opener?.isConnected) {
        opener.focus();
      }
    };
    const handleCancel = (event: Event) => {
      event.preventDefault();
      dialog.close();
    };
    dialog.addEventListener('close', handleClose);
    dialog.addEventListener('cancel', handleCancel);
    return () => {
      dialog.removeEventListener('close', handleClose);
      dialog.removeEventListener('cancel', handleCancel);
    };
  }, [onClose]);

  return (
    <dialog className="dialog" ref={dialogRef} aria-labelledby={titleId}>
      <div className="dialog__body">
        <h2 id={titleId} tabIndex={-1} data-dialog-initial-focus>
          {title}
        </h2>
        {children}
        <div className="action-group">
          <button
            type="button"
            className="action action--secondary"
            onClick={() => {
              dialogRef.current?.close();
            }}
          >
            {closeLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
