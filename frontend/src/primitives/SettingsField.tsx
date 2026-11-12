import type { ReactNode } from 'react';

/**
 * settings-field (UX-DR25): persistent label and description above the control; validation and
 * help stay visible. Saving is explicit and happens through an ActionButton beside the field.
 */
export interface SettingsFieldProps {
  id: string;
  label: string;
  description: string;
  children: ReactNode;
  validation?: string;
  /** Use a fieldset/legend when the control is a group of inputs (radio choices). */
  group?: boolean;
}

export function SettingsField({ id, label, description, children, validation, group = false }: SettingsFieldProps) {
  const descriptionId = `${id}-description`;
  const validationId = `${id}-validation`;
  const content = (
    <>
      <p className="settings-field__description" id={descriptionId}>
        {description}
      </p>
      {children}
      <p className="settings-field__description" id={validationId} role="status">
        {validation ?? ''}
      </p>
    </>
  );
  if (group) {
    return (
      <fieldset className="settings-field" id={id} aria-describedby={`${descriptionId} ${validationId}`}>
        <legend className="settings-field__label">{label}</legend>
        {content}
      </fieldset>
    );
  }
  return (
    <div className="settings-field">
      <label className="settings-field__label" htmlFor={id}>
        {label}
      </label>
      {content}
    </div>
  );
}
