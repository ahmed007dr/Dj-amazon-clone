import './ColorField.css';

/**
 * حقل لون.
 *
 * ⚠️  منتقي لوني **وحقل نصي معًا**.
 *
 *     المنتقي وحده يمنع لصق كود العلامة التجارية الدقيق؛ والحقل
 *     وحده يجبر على معرفة الست عشري. الاثنان يغطّيان الحالتين.
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
            // ⚠️  لا نمرّر قيمة ناقصة إلى المنتقي: `#ab` يجعله يقفز
            //     إلى الأسود بينما المستخدم في منتصف الكتابة.
            if (/^#[0-9a-fA-F]{0,6}$/.test(next)) onChange(next);
          }}
        />
      </span>
    </label>
  );
}
