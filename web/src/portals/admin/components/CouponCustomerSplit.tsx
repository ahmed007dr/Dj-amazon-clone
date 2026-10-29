import { useTranslation } from 'react-i18next';

import './CouponReport.css';

export interface SplitSide {
  /** What sizes the bar segment (orders, or a discount amount). */
  weight: number;
  /** The main figure in words: "12 orders". */
  headline: string;
  /** A second line: "3 customers · 1,200 EGP". */
  detail?: string;
}

/**
 * The registered-vs-guest split as one two-segment bar.
 *
 * ⚠️  **Never colour alone.** Registered is solid, guest is hatched, and both are named in
 *     text with their figures and their share underneath — the bar is the picture of the
 *     list below it, not a replacement for it. A reader who cannot tell green from blue
 *     (or prints it in grey) loses nothing.
 *
 * ⚠️  The share is computed from the **weights the server sent**, only to size the bar and
 *     print a percentage — the figures themselves are the server's own strings.
 *
 * ⚠️  The segments have a 2px gap of the surface colour between them, and an empty split
 *     (no sales yet) draws an empty track rather than two half-bars implying 50/50.
 */
export function CouponCustomerSplit({
  title,
  registered,
  guest,
}: {
  title: string;
  registered: SplitSide;
  guest: SplitSide;
}) {
  const { t, i18n } = useTranslation();

  const total = registered.weight + guest.weight;
  const share = (weight: number) => (total > 0 ? (weight / total) * 100 : 0);
  const percent = (weight: number) =>
    new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 0 }).format(share(weight)) + '%';

  const sides = [
    { key: 'registered', label: t('pricing.report.registered'), side: registered },
    { key: 'guest', label: t('pricing.report.guest'), side: guest },
  ] as const;

  return (
    <section className="report-split surface" aria-label={title}>
      <h3>{title}</h3>

      <div
        className="report-split__bar"
        dir="ltr"
        role="img"
        aria-label={sides
          .map(({ label, side }) => `${label}: ${side.headline} (${percent(side.weight)})`)
          .join(' · ')}
      >
        {total > 0 ? (
          sides.map(({ key, side }) => (
            <span
              key={key}
              className={`report-split__seg is-${key}`}
              style={{ flexBasis: `${String(share(side.weight))}%` }}
            />
          ))
        ) : (
          <span className="report-split__seg is-empty" />
        )}
      </div>

      <ul className="report-split__legend">
        {sides.map(({ key, label, side }) => (
          <li key={key}>
            <span className={`report-split__swatch is-${key}`} aria-hidden />
            <span className="report-split__text">
              <strong>
                {label} <span className="report-split__pct">{total > 0 ? percent(side.weight) : '—'}</span>
              </strong>
              <span>{side.headline}</span>
              {side.detail ? <small>{side.detail}</small> : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
