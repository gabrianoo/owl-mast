/**
 * Primary destinations (EXPERIENCE.md information architecture, navigation reference). Feature
 * content arrives with later epics; the shell owns the route, title, heading and honest first-use
 * state of each destination. Nothing here invents counts, progress or data.
 */
export type DestinationId = 'daily-work' | 'focus' | 'knowledge' | 'connections' | 'usage' | 'preferences';

export interface Destination {
  id: DestinationId;
  path: string;
  label: string;
  heading: string;
  lede: string;
  /** Empty/first-use message shown until the destination has authorized content. */
  firstUse: { title: string; body: string };
}

export const APP_NAME = 'Owl Mast';

export const HOME: Destination = {
  id: 'daily-work',
  path: '/',
  label: 'Daily Work',
  heading: 'Daily Work',
  lede: 'Progress, attention, agent observations and shared learning for the authorized scope.',
  firstUse: {
    title: 'No authorized project yet',
    body: 'Daily Work shows observed work once a project is authorized for this session. Sign-in and project authorization are not part of this version of the shell.',
  },
};

export const PREFERENCES: Destination = {
  id: 'preferences',
  path: '/preferences',
  label: 'Preferences',
  heading: 'Preferences',
  lede: 'Theme and notification settings for this browser.',
  firstUse: {
    title: 'Preferences',
    body: 'Settings save explicitly and report their actual result.',
  },
};

export const DESTINATIONS: readonly Destination[] = [
  HOME,
  {
    id: 'focus',
    path: '/focus',
    label: 'Focus',
    heading: 'Focus',
    lede: 'Work assigned to you across authorized projects, grouped by epic, combined or as a board.',
    firstUse: {
      title: 'No assigned work to show',
      body: 'Focus lists work assigned to you once a project is authorized and your identity in its sources is confirmed. Nothing is hidden here; there is no authorized project in this session.',
    },
  },
  {
    id: 'knowledge',
    path: '/knowledge',
    label: 'Knowledge',
    heading: 'Knowledge',
    lede: 'Scoped catalog, lifecycle states and exact-version lineage for permitted knowledge.',
    firstUse: {
      title: 'No authorized scope for knowledge',
      body: 'Knowledge opens in an authorized project. This session has none, so no catalog or search is available.',
    },
  },
  {
    id: 'connections',
    path: '/connections',
    label: 'Connections',
    heading: 'Connections',
    lede: 'Enrolled Claude and Codex clients, their readiness and observed locations.',
    firstUse: {
      title: 'No enrolled clients',
      body: 'Connections lists enrolled clients once enrollment is available for an authorized project. Nothing is enrolled in this session.',
    },
  },
  {
    id: 'usage',
    path: '/usage',
    label: 'Usage',
    heading: 'Usage',
    lede: 'Observed usage, estimates, allocations and bills kept as separate measurement classes.',
    firstUse: {
      title: 'No observed usage',
      body: 'Usage reports observed records for an authorized scope and period. This session has no authorized scope; unavailable is not zero.',
    },
  },
  PREFERENCES,
];


export function findDestination(pathname: string): Destination | undefined {
  return DESTINATIONS.find((destination) => destination.path === pathname);
}

export function pageTitle(heading: string): string {
  return `${heading} · ${APP_NAME}`;
}
