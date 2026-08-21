import { useId, type InputHTMLAttributes } from 'react';

import './Field.css';

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string | undefined;
  hint?: string | undefined;
}

/**
 * An input field with a label and an error bound to it.
 *
 * ⚠️  `useId`, not a random number and not the field's name.
 *
 *     An unbound label means clicking it does not focus the field, and the
 *     screen reader announces "text field" with no name. And `aria-describedby`
 *     is what makes it speak the error message instead of leaving it as red text
 *     they cannot see.
 */
export function Field({ label, error, hint, id, ...rest }: Props) {
  const generated = useId();
  const inputId = id ?? generated;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;

  const describedBy = [error ? errorId : null, hint ? hintId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="field">
      <label className="field__label" htmlFor={inputId}>
        {label}
      </label>

      <input
        id={inputId}
        className={`field__input ${error ? 'has-error' : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        {...rest}
      />

      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}

      {error ? (
        <p id={errorId} className="field__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
