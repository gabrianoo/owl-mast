import { useState } from 'react';
import { PREFERENCES } from '../app/destinations.ts';
import { ActionButton, type ActionOutcome } from '../primitives/ActionButton.tsx';
import { SettingsField } from '../primitives/SettingsField.tsx';
import { StateMessage } from '../primitives/StateMessage.tsx';
import { THEME_PREFERENCES, describePreference, type ThemePreference } from '../theme/themePreference.ts';
import { useTheme } from '../theme/ThemeProvider.tsx';
import { DestinationPage } from './DestinationPage.tsx';

const PREFERENCE_LABEL: Record<ThemePreference, string> = {
  system: 'Follow device',
  light: 'Light',
  dark: 'Dark',
};

export function Preferences() {
  return (
    <DestinationPage destination={PREFERENCES}>
      <ThemeSettings />
      <section className="panel" aria-labelledby="notifications-heading">
        <h2 id="notifications-heading">Notifications</h2>
        <StateMessage kind="unsupported" title="Push notifications are not offered in this version" as="h3">
          <p>
            Nothing has been requested from your device and no notification setting is stored. Push delivery stays an
            explicit qualification gate; work updates are not pushed from this shell.
          </p>
        </StateMessage>
      </section>
    </DestinationPage>
  );
}

export function ThemeSettings() {
  const theme = useTheme();
  const [draft, setDraft] = useState<ThemePreference>(theme.preference);
  const unsaved = draft !== theme.preference;

  const save = async (): Promise<ActionOutcome> => {
    const chosen = draft;
    try {
      await theme.save(chosen);
      return { ok: true, message: `Theme saved: ${PREFERENCE_LABEL[chosen]}.` };
    } catch {
      return { ok: false, message: `The theme could not be saved in this browser. Your choice (${PREFERENCE_LABEL[chosen]}) is kept here until you try again.` };
    }
  };

  return (
    <section className="panel" aria-labelledby="appearance-heading">
      <h2 id="appearance-heading">Appearance</h2>
      <SettingsField
        id="theme"
        group
        label="Theme"
        description={`Current: ${describePreference(theme.preference, theme.resolved)}. Following the device uses your system light or dark setting; an explicit choice overrides it on this browser.`}
        validation={unsaved ? `Unsaved change: ${PREFERENCE_LABEL[draft]}. Save to apply it.` : 'No unsaved changes.'}
      >
        <div className="choice-list" role="radiogroup" aria-label="Theme">
          {THEME_PREFERENCES.map((preference) => (
            <label key={preference} className="choice">
              <input
                type="radio"
                name="theme"
                value={preference}
                checked={draft === preference}
                onChange={() => {
                  setDraft(preference);
                }}
              />
              {PREFERENCE_LABEL[preference]}
            </label>
          ))}
        </div>
      </SettingsField>
      <ActionButton onAction={save}>Save theme</ActionButton>
    </section>
  );
}
