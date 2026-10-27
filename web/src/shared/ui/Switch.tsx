import type { ReactNode } from 'react';

import './Switch.css';

/**
 * An on/off switch — a row, not just the track.
 *
 * ⚠️  The **whole row is the label**, so the whole row is the hit area.
 *
 *     A bare 2.75rem track at the far end of a wide card is a precise target a
 *     finger misses, and the user then taps the *name* they just read and nothing
 *     happens. Wrapping icon + text + track in one `<label>` makes any tap on
 *     the row toggle it, and gives the control its accessible name for free.
 *
 * ⚠️  A real `<input type="checkbox" role="switch">`, not a styled `<div>`.
 *
 *     Keyboard (Space), focus, forms and screen readers ("on"/"off") come from
 *     the platform instead of being re-implemented badly. The input is only
 *     *visually* replaced by the track beside it.
 *
 * ⚠️  The thumb is positioned with `inset-inline-start`, not `translateX`, so it
 *     travels towards the *end* edge in both directions — a switch whose "on"
 *     side stays on the right inside an Arabic page reads backwards.
 *
 * ⚠️  `loading` is **not** `disabled`.
 *
 *     A disabled input loses keyboard focus the instant it is set, which throws
 *     a keyboard user off the control they just pressed. While loading, the input
 *     stays focusable and further changes are simply ignored; `aria-busy` tells
 *     assistive technology why nothing happened. `disabled` is for "this can
 *     never change" (a mandatory preference).
 */
export function Switch({
  checked,
  onChange,
  label,
  description,
  icon,
  hideLabel = false,
  disabled = false,
  loading = false,
  className,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Also the accessible name. May carry inline extras such as a `Badge`. */
  label: ReactNode;
  /** A secondary line under the label (linked via the label, so it is announced too). */
  description?: ReactNode;
  /** Decorative — placed at the start edge. */
  icon?: ReactNode;
  /** Keep the label for assistive technology only. */
  hideLabel?: boolean;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}) {
  const classes = [
    'switch',
    checked ? 'is-on' : '',
    disabled ? 'is-disabled' : '',
    loading ? 'is-loading' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <label className={classes}>
      {icon ? (
        <span className="switch__icon" aria-hidden>
          {icon}
        </span>
      ) : null}

      <span className={hideLabel ? 'visually-hidden' : 'switch__text'}>
        <span className="switch__label">{label}</span>
        {description ? <span className="switch__desc">{description}</span> : null}
      </span>

      <input
        type="checkbox"
        role="switch"
        className="switch__input"
        checked={checked}
        aria-checked={checked}
        aria-busy={loading || undefined}
        disabled={disabled}
        onChange={(event) => {
          if (loading) return;
          onChange(event.target.checked);
        }}
      />
      <span className="switch__track" aria-hidden>
        <span className="switch__thumb" />
      </span>
    </label>
  );
}
