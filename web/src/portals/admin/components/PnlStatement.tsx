import { useTranslation } from 'react-i18next';

import type { ProfitAndLoss } from '@/features/finance/api';

import './PnlStatement.css';

/**
 * The profit and loss statement.
 *
 * ⚠️  **Presented as a stepped equation rather than scattered cards.**
 *
 *     "Revenue", "cost" and "profit" cards side by side read as independent
 *     figures, so the reader cannot see **how** the profit reached what it is.
 *     The stepping, with subtraction lines, makes "where did the money go?"
 *     answerable at a glance.
 *
 * ⚠️  And what is subtracted is shown with an explicit negative sign.
 *
 *     A positive number on the "cost" line is misread as an addition to the
 *     profit — and the difference between those two readings is the entire
 *     value of the statement.
 */
export function PnlStatement({ report }: { report: ProfitAndLoss }) {
  const { t } = useTranslation();

  const negative = (value: string) => {
    const number = Number(value);
    return number === 0 ? '0.00' : `−${Math.abs(number).toFixed(2)}`;
  };

  return (
    <table className="pnl">
      <tbody>
        <tr>
          <th scope="row">{t('finance.revenue')}</th>
          <td dir="ltr">{report.revenue}</td>
        </tr>
        <tr className="pnl__minus">
          <th scope="row">{t('finance.refunds')}</th>
          <td dir="ltr">{negative(report.refunds)}</td>
        </tr>
        <tr className="pnl__subtotal">
          <th scope="row">{t('finance.netSales')}</th>
          <td dir="ltr">{report.net_sales}</td>
        </tr>

        <tr className="pnl__minus">
          <th scope="row">{t('finance.cogs')}</th>
          <td dir="ltr">{negative(report.cogs)}</td>
        </tr>
        <tr className="pnl__subtotal">
          <th scope="row">{t('finance.grossProfit')}</th>
          <td dir="ltr">
            {report.gross_profit}
            <span className="pnl__margin">{report.gross_margin}%</span>
          </td>
        </tr>

        <tr className="pnl__minus">
          <th scope="row">{t('finance.expenses')}</th>
          <td dir="ltr">{negative(report.expenses)}</td>
        </tr>
        <tr className={`pnl__total ${Number(report.net_profit) < 0 ? 'is-loss' : ''}`}>
          <th scope="row">{t('finance.netProfit')}</th>
          <td dir="ltr">{report.net_profit}</td>
        </tr>
      </tbody>

      <tfoot>
        {/* ⚠️  Tax collected is **outside the equation** — displayed for information.
            It is held on the state's behalf rather than being revenue, and
            including it in the lines above inflated the profit by its full rate. */}
        <tr>
          <th scope="row">{t('finance.taxCollected')}</th>
          <td dir="ltr">{report.tax_collected}</td>
        </tr>
      </tfoot>
    </table>
  );
}
