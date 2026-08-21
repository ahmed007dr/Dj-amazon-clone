import './ColorField.css';

/**
 * A colour field.
 *
 * ⚠️  A colour picker **and a text field together**.
 *
 *     The picker alone prevents pasting the exact brand code; and the field
 *     alone forces the user to know hex. The two together cover both cases.
 */
export function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="color-field">
      <span className="color-field__label">{label}</span>

      <span className="color-field__inputs">
        <input
          type="color"
          className="color-field__picker"
          value={value}
          aria-label={label}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />

        <input
          type="text"
          className="color-field__text"
          value={value}
          maxLength={7}
          spellCheck={false}
          onChange={(event) => {
            const next = event.target.value;
            // ⚠️  We do not pass an incomplete value to the picker: `#ab` makes it jump
            //     to black while the user is mid-typing.
            if (/^#[0-9a-fA-F]{0,6}$/.test(next)) onChange(next);
          }}
        />
      </span>
    </label>
  );
}
