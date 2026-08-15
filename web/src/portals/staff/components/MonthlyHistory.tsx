import { useTranslation } from 'react-i18next';

import type { MonthRow } from '@/features/employees/api';
import { StateMessage } from '@/shared/ui/StateMessage';

import './MonthlyHistory.css';

/**
 * أداء الأشهر السابقة.
 *
 * ⚠️  **الصافي عمود مستقل لا فرق يُحسب بالنظر.**
 *
 *     المندوب يقارن شهره بما قبله؛ وإجباره على طرح المرتجعات من
 *     الإجمالي في رأسه يجعله يقارن الأرقام الخطأ.
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
