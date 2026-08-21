import { useTranslation } from 'react-i18next';

import { StateMessage } from '@/shared/ui/StateMessage';

import './TrendBars.css';

/**
 * A daily trend in bars.
 *
 * ⚠️  **Empty days are absent — and the difference is deliberate.**
 *
 *     The server returns only the days a sale occurred on. Drawing a zero day
 *     requires filling the gaps, which hides the fact that the day **had
 *     nothing recorded** behind a zero-height bar that reads as data.
 */
export function TrendBars({ rows }: { rows: { label: string; value: number }[] }) {
  const { t } = useTranslation();

  if (rows.length === 0) {
    return <StateMessage icon="—" title={t('reports.noSales')} />;
  }

  const top = Math.max(...rows.map((row) => row.value), 1);

  return (
    <div className="trend" role="img" aria-label={t('reports.dailyTrend')}>
      {rows.map((row) => (
        <div key={row.label} className="trend__col">
          <span
            className="trend__bar"
            style={{ blockSize: `${Math.max((row.value / top) * 100, 2)}%` }}
            title={`${row.label}: ${row.value.toFixed(2)}`}
          />
          <span className="trend__label" dir="ltr">
            {row.label}
          </span>
        </div>
      ))}
    </div>
  );
}
