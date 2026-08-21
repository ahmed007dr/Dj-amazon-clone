import { useTranslation } from 'react-i18next';

import type { ContrastEntry } from '../adminApi';

import './ContrastReport.css';

/**
 * The contrast report.
 *
 * ⚠️  **The passing and the failing are shown together**, not the failing alone.
 *
 *     Showing what passes lets the admin see the effect of their edit moment by
 *     moment: the ratio moves with every colour change, so they close in on the
 *     threshold instead of guessing.
 *
 * ⚠️  And the 4.5:1 threshold is not an aesthetic opinion — light grey text on
 *     white looks elegant on a designer's monitor and is unreadable on a phone in sunlight.
 */
export function ContrastReport({ entries }: { entries: ContrastEntry[] }) {
  const { t } = useTranslation();

  const failing = entries.filter((entry) => !entry.passes_aa).length;

  return (
    <div className="contrast">
      <p className={`contrast__summary ${failing > 0 ? 'is-failing' : ''}`}>
        {failing === 0
          ? t('admin.contrastAllPass')
          : t('admin.contrastFailing', { count: failing })}
      </p>

      <ul className="contrast__list">
        {entries.map((entry) => (
          <li key={entry.key} className="contrast__row">
            <span
              className="contrast__swatch"
              style={{ background: entry.background, color: entry.foreground }}
              aria-hidden
            >
              Aa
            </span>

            <span className="contrast__label">{entry.label}</span>

            <span className={`contrast__ratio ${entry.passes_aa ? 'is-pass' : 'is-fail'}`}>
              {entry.ratio}:1
            </span>

            <span aria-hidden>{entry.passes_aa ? '✓' : '✕'}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
