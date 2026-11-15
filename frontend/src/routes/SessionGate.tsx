import type { ReactNode } from 'react';
import { StateMessage } from '../primitives/StateMessage.tsx';
import { useSession } from '../state/session.tsx';

/**
 * Shows content that needs authorization only to a signed-in person (OM-02.01). Every other session
 * state replaces the content with its own message and next step, so nothing protected stays on the
 * page after a session ended and nothing is shown while the session is unknown.
 */
export function SessionGate({ subject, children }: { subject: string; children: ReactNode }) {
  const { state, signIn, refresh } = useSession();

  switch (state.kind) {
    case 'signed-in':
      return <>{children}</>;
    case 'loading':
      return (
        <StateMessage kind="loading" title="Checking your session" as="h2">
          <p>{subject} appears once Owl Mast knows whether you are signed in.</p>
        </StateMessage>
      );
    case 'signed-out':
      return (
        <StateMessage
          kind="signed-out"
          title="You are signed out"
          as="h2"
          action={
            <button type="button" className="action action--primary" onClick={signIn}>
              Sign in
            </button>
          }
        >
          <p>
            Sign in to see {subject}. Sign-in happens at your identity provider; accounts are created by an administrator
            there, and Owl Mast never sees your password.
          </p>
          {state.identityProvider === 'unconfirmed' ? (
            <p>
              Owl Mast ended its session, but could not confirm that the identity provider ended its own. Close this
              browser, or sign out at the identity provider, if someone else uses this device.
            </p>
          ) : null}
        </StateMessage>
      );
    case 'expired':
      return (
        <StateMessage
          kind="signed-out"
          title="Your session ended"
          as="h2"
          focusOnMount
          action={
            <button type="button" className="action action--primary" onClick={signIn}>
              Sign in again
            </button>
          }
        >
          <p>
            The session expired or was ended, so content that needs authorization was removed from this page. Sign in
            again to continue.
          </p>
        </StateMessage>
      );
    case 'sign-in-failed':
      return (
        <StateMessage
          kind="denied"
          title="Sign-in was not completed"
          as="h2"
          action={
            <button type="button" className="action action--primary" onClick={signIn}>
              Sign in again
            </button>
          }
        >
          <p>
            The identity provider did not confirm a sign-in, or it was cancelled. Nobody is signed in. If you have no
            account yet, an administrator has to create it first.
          </p>
        </StateMessage>
      );
    case 'provider-error':
      return (
        <StateMessage
          kind="error"
          title="The identity provider is unavailable"
          as="h2"
          action={
            <button type="button" className="action action--primary" onClick={signIn}>
              Retry sign-in
            </button>
          }
        >
          <p>Sign-in could not continue because the identity provider did not answer. Nobody is signed in.</p>
        </StateMessage>
      );
    case 'problem':
      return (
        <StateMessage
          kind="error"
          title="The session could not be checked"
          as="h2"
          action={
            <button type="button" className="action action--secondary" onClick={refresh}>
              Retry
            </button>
          }
        >
          <p>
            Owl Mast could not confirm whether you are signed in, so nothing that needs authorization is shown.
          </p>
        </StateMessage>
      );
  }
}
