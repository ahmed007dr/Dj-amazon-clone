import { useTranslation } from 'react-i18next';

import './QuantityStepper.css';

/**
 * ⚠️  أزرار لا حقل رقمي وحده.
 *
 *     `<input type="number">` على الهاتف يفتح لوحة أرقام ويحتاج
 *     ثلاث لمسات لزيادة واحدة. الأزرار تجعلها لمسة، والحقل يبقى
 *     للإدخال المباشر حين تكون الكمية كبيرة.
 */
export function QuantityStepper({
  value,
  onChange,
  disabled = false,
  max = 999,
}: {
  value: number;
  onChange: (next: number) => void;
  disabled?: boolean;
  max?: number;
}) {
  const { t } = useTranslation();

  const clamp = (next: number) => Math.min(Math.max(next, 0), max);

  return (
    <div className="qty">
      <button
        type="button"
        className="qty__button"
        aria-label={t('cart.decrease')}
        disabled={disabled || value <= 0}
        onClick={() => {
          onChange(clamp(value - 1));
        }}
      >
        −
      </button>

      <input
        type="number"
        className="qty__input"
        value={value}
        min={0}
        max={max}
        disabled={disabled}
        aria-label={t('cart.quantity')}
        onChange={(event) => {
          const next = Number.parseInt(event.target.value, 10);
          onChange(Number.isNaN(next) ? 0 : clamp(next));
        }}
      />

      <button
        type="button"
        className="qty__button"
        aria-label={t('cart.increase')}
        disabled={disabled || value >= max}
        onClick={() => {
          onChange(clamp(value + 1));
        }}
      >
        +
      </button>
    </div>
  );
}
