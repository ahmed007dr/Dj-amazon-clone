import { useTranslation } from 'react-i18next';

import type { MonthRow } from '@/features/employees/api';
import { StateMessage } from '@/shared/ui/StateMessage';

import './MonthlyHistory.css';

/**
 * Performance over previous months.
 *
 * ⚠️  **Net is its own column, not a difference worked out by eye.**
 *
 *     The rep compares this month with the one before; and forcing them to
 *     subtract returns from the total in their head makes them compare the wrong numbers.
 */
export function MonthlyHistory({ rows }: { rows: MonthRow[] }) {
  const { t } = useTranslation();

  if (rows.length === 0) {
    return <StateMessage icon="📈" title={t('staff.noHistory')} />;
  }

  return (
    <section className="month-history">
      <h2>{t('staff.history')}</h2>

      <div className="month-history__scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('staff.month')}</th>
              <th scope="col">{t('staff.ordersCount')}</th>
              <th scope="col">{t('staff.gross')}</th>
              <th scope="col">{t('staff.returns')}</th>
              <th scope="col">{t('staff.netSales')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.month}>
                <td dir="ltr">{row.month}</td>
                <td dir="ltr">{row.orders}</td>
                <td dir="ltr">{row.gross}</td>
                <td dir="ltr">{row.returns}</td>
                <td dir="ltr">
                  <strong>{row.net}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
