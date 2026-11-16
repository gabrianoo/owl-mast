import { ActionButton } from '../../primitives/ActionButton.tsx';
import { useSession } from '../../state/session.tsx';

/**
 * Session control in the shell header (OM-02.01): the signed-in person's display name as text and
 * the sign-out action, or the sign-in action when nobody is signed in. The name is display only;
 * the identity provider owns the account, its password and its recovery.
 *
 * When a session is kept and cannot be confirmed (somebody was signed in before the reads failed, or
 * the backend said so in the failed read, as it does for a shell that starts during an identity
 * provider outage), no name is shown and sign-out is offered: the backend ends the session on
 * request even while the identity provider is unavailable, and that is when a person on a shared
 * device needs it.
 */
export function SessionControl() {
  const { state, signIn, signOut } = useSession();

  if (state.kind === 'loading') {
    return (
      <div className="session-control" role="group" aria-label="Session">
        <p className="session-control__person" role="status">
          Checking your session…
        </p>
      </div>
    );
  }
  if (state.kind === 'problem') {
    return (
      <div className="session-control" role="group" aria-label="Session">
        <p className="session-control__person" role="status">
          Session not confirmed
        </p>
        {state.afterSignedIn ? (
          <ActionButton variant="secondary" onAction={signOut} pendingLabel="Signing out…">
            Sign out
          </ActionButton>
        ) : null}
      </div>
    );
  }
  if (state.kind === 'signed-in') {
    return (
      <div className="session-control" role="group" aria-label="Session">
        <p className="session-control__person">
          Signed in as <strong>{state.person.displayName}</strong>
        </p>
        <ActionButton variant="secondary" onAction={signOut} pendingLabel="Signing out…">
          Sign out
        </ActionButton>
      </div>
    );
  }
  return (
    <div className="session-control" role="group" aria-label="Session">
      <p className="session-control__person">Signed out</p>
      <button type="button" className="action action--secondary" onClick={signIn}>
        Sign in
      </button>
    </div>
  );
}
