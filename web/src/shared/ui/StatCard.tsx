import type { ReactNode } from 'react';

import './StatCard.css';

/**
 * A figure card on the dashboard.
 *
 * ⚠️  A number with no context means nothing: is "12" orders many or few?
 *     Which is why `hint` is not decoration — it is what turns the number into
 *     information.
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
