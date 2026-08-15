import { useTranslation } from 'react-i18next';

import type { ProfitAndLoss } from '@/features/finance/api';

import './PnlStatement.css';

/**
 * قائمة الأرباح والخسائر.
 *
 * ⚠️  **تُعرَض كمعادلة متدرّجة لا كبطاقات مبعثرة.**
 *
 *     بطاقات «إيراد» و«تكلفة» و«ربح» متجاورة تُقرأ كأرقام مستقلة،
 *     فلا يرى القارئ **كيف** وصل الربح إلى ما هو عليه. التدرّج
 *     بخطوط الطرح يجعل السؤال «أين ذهب المال؟» يُجاب بالنظر.
 *
 * ⚠️  والمطروح يُعرَض بإشارة سالبة صريحة.
 *
 *     رقم موجب في سطر «التكلفة» يُقرأ خطأً كإضافة إلى الربح —
 *     والفرق بين قراءتين هو كل الفائدة من القائمة.
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
        {/* ⚠️  الضريبة المحصَّلة **خارج المعادلة** — تُعرَض للعلم.
            هي أمانة للدولة لا إيراد، وإدراجها في السطور أعلاه
            كان يضخّم الربح بنسبتها كاملة. */}
        <tr>
          <th scope="row">{t('finance.taxCollected')}</th>
          <td dir="ltr">{report.tax_collected}</td>
        </tr>
      </tfoot>
    </table>
  );
}
