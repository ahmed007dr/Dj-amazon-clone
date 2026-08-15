import { useTranslation } from 'react-i18next';

import type { Statement } from '@/features/b2b/api';
import { formatDate } from '@/shared/utils/format';

import './StatementTable.css';

/**
 * كشف الحساب.
 *
 * ⚠️  **الرصيد الجاري عمود لا حاشية.**
 *
 *     العميل يراجع الكشف ليجد أين اختلف رقمه عن رقمنا. بلا رصيد
 *     متراكم بعد كل حركة عليه أن يجمع بنفسه — وهو ما يجعل النزاع
 *     يطول بلا سبب.
 *
 * ⚠️  والمدين والدائن عمودان منفصلان لا عمود بإشارة.
 *
 *     هكذا يقرأه المحاسب، وهكذا يطابقه بدفتره. عمود واحد بسالب
 *     وموجب يجبره على الترجمة في رأسه.
 */
export function StatementTable({ statement }: { statement: Statement }) {
  const { t, i18n } = useTranslation();

  let running = Number(statement.opening_balance);

  return (
    <div className="statement">
      <div className="statement__aging">
        {statement.aging.map((bucket) => (
          <div key={bucket.label} className="statement__bucket">
            <span>{t(`b2b.aging.${bucket.label}`, { defaultValue: bucket.label })}</span>
            <strong dir="ltr">{bucket.amount}</strong>
          </div>
        ))}
      </div>

      <div className="statement__scroll">
        <table className="statement__table">
          <thead>
            <tr>
              <th scope="col">{t('b2b.date')}</th>
              <th scope="col">{t('b2b.description')}</th>
              <th scope="col">{t('b2b.debit')}</th>
              <th scope="col">{t('b2b.credit')}</th>
              <th scope="col">{t('b2b.balance')}</th>
            </tr>
          </thead>

          <tbody>
            <tr className="statement__opening">
              <td colSpan={4}>{t('b2b.openingBalance')}</td>
              <td dir="ltr">{statement.opening_balance}</td>
            </tr>

            {statement.entries.map((entry) => {
              running += entry.is_debit ? Number(entry.amount) : -Number(entry.amount);
              return (
                <tr key={entry.id}>
                  <td>{formatDate(entry.occurred_on, i18n.language)}</td>
                  <td>
                    {t(`b2b.ledgerKind.${entry.kind}`)}
                    {entry.reference ? <code> {entry.reference}</code> : null}
                  </td>
                  <td dir="ltr">{entry.is_debit ? entry.amount : '—'}</td>
                  <td dir="ltr">{entry.is_debit ? '—' : entry.amount}</td>
                  <td dir="ltr">{running.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>

          <tfoot>
            <tr>
              <td colSpan={4}>{t('b2b.closingBalance')}</td>
              <td dir="ltr">{statement.closing_balance}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
