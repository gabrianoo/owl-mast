import { useId, useState } from 'react';
import { ModalDialog } from '../../primitives/ModalDialog.tsx';
import { StateMessage } from '../../primitives/StateMessage.tsx';
import { describePeriod, describeProject, describeSourceIdentity, useScope } from '../../state/scope.tsx';

/**
 * scope-bar (UX-DR08): project/company, source identity and period remain visible and wrap on
 * phone. Changing scope opens the authorized-project chooser; the shell never substitutes a project.
 */
export function ScopeBar() {
  const scope = useScope();
  const [chooserOpen, setChooserOpen] = useState(false);
  const headingId = useId();

  return (
    <section className="scope-bar" aria-labelledby={headingId}>
      <h2 id={headingId} className="visually-hidden">
        Viewing scope
      </h2>
      <dl className="scope-bar__facts">
        <div className="scope-bar__fact">
          <dt>Project</dt>
          <dd>{describeProject(scope.project)}</dd>
        </div>
        <div className="scope-bar__fact">
          <dt>Source identity</dt>
          <dd>{describeSourceIdentity(scope.sourceIdentity)}</dd>
        </div>
        <div className="scope-bar__fact">
          <dt>Period</dt>
          <dd>{describePeriod(scope.period)}</dd>
        </div>
      </dl>
      <button
        type="button"
        className="action action--secondary"
        onClick={() => {
          setChooserOpen(true);
        }}
      >
        Change scope
      </button>
      <ModalDialog
        open={chooserOpen}
        title="Choose an authorized project"
        onClose={() => {
          setChooserOpen(false);
        }}
      >
        <StateMessage kind="empty" title="No authorized projects are available in this session">
          <p>
            Sign-in and project authorization are not part of this version of the shell. Nothing is hidden: this
            session has no authorized project, so no project can be selected yet.
          </p>
        </StateMessage>
      </ModalDialog>
    </section>
  );
}
