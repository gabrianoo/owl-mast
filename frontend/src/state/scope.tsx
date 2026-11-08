import { createContext, useContext, useMemo, type ReactNode } from 'react';

/**
 * Viewing scope (scope-bar contract): project or company, source identity and reporting period
 * remain visible on every surface. Authorization and project selection arrive with E02; until then
 * the scope is explicitly "none" and the shell says so instead of substituting a project.
 */
export interface ScopeState {
  project: { kind: 'none' } | { kind: 'project'; name: string } | { kind: 'company' };
  sourceIdentity: 'unconfirmed' | 'confirmed';
  period: { kind: 'today'; timeZone: string };
}

const ScopeContext = createContext<ScopeState | null>(null);

export function viewerTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function ScopeProvider({ children, initial }: { children: ReactNode; initial?: ScopeState }) {
  const value = useMemo<ScopeState>(
    () =>
      initial ?? {
        project: { kind: 'none' },
        sourceIdentity: 'unconfirmed',
        period: { kind: 'today', timeZone: viewerTimeZone() },
      },
    [initial],
  );
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope(): ScopeState {
  const value = useContext(ScopeContext);
  if (!value) {
    throw new Error('useScope requires ScopeProvider');
  }
  return value;
}

export function describeProject(project: ScopeState['project']): string {
  switch (project.kind) {
    case 'none':
      return 'No project selected';
    case 'company':
      return 'Company · authorized projects';
    case 'project':
      return project.name;
  }
}

export function describeSourceIdentity(identity: ScopeState['sourceIdentity']): string {
  return identity === 'confirmed' ? 'Confirmed' : 'Not confirmed';
}

export function describePeriod(period: ScopeState['period']): string {
  return `Today · ${period.timeZone}`;
}
