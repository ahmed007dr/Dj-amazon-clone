import type { ReactNode } from 'react';

import './StatCard.css';

/**
 * بطاقة رقم في لوحة المعلومات.
 *
 * ⚠️  الرقم بلا سياق لا يعني شيئًا: «١٢» طلبًا كثير أم قليل؟
 *     ولذلك `hint` ليس زخرفة — هو ما يحوّل الرقم إلى معلومة.
 */
export function StatCard({
  label,
  value,
  hint,
  tone = 'neutral',
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
  icon?: ReactNode;
}) {
  return (
    <article className={`stat-card surface stat-card--${tone}`}>
      {icon ? (
        <span className="stat-card__icon" aria-hidden>
          {icon}
        </span>
      ) : null}

      <div className="stat-card__body">
        <p className="stat-card__label muted">{label}</p>
        <p className="stat-card__value">{value}</p>
        {hint ? <p className="stat-card__hint muted">{hint}</p> : null}
      </div>
    </article>
  );
}
