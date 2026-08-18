import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAdminLedger, type BusinessProfile } from '@/features/b2b/api';
import { Badge } from '@/shared/ui/Badge';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './BusinessPanels.css';

const KIND_TONE: Record<string, 'danger' | 'success' | 'info' | 'neutral'> = {
  CHARGE: 'danger',
  PAYMENT: 'success',
  CREDIT_NOTE: 'info',
  ADJUSTMENT: 'neutral',
};

/**
 * حركات حساب العميل التجاري.
 *
 * ⚠️  **الاتجاه يُقرأ من الإشارة واللون معًا لا من النوع.**
 *
 *     «إشعار دائن» و«دفعة» كلاهما ينقص الدَّين، و«فاتورة» تزيده.
 *     من يقرأ الكشف يريد أن يعرف «زاد أم نقص» قبل أن يقرأ اسم
 *     الحركة — وخلط الاتجاهين هو كيف يُقرأ ما علينا كأنه لنا.
 *
 * ⚠️  و**هذا الكشف مفصَّل لا مُجمَّع**: كشف الحساب في لوح الائتمان
 *     يعطي الأرصدة والأعمار، وهذا يعطي كل حركة على حدة — سؤالان
 *     مختلفان لا نسختان من سؤال.
 */
export function BusinessLedgerPanel({ business }: { business: BusinessProfile }) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const ledger = useAdminLedger(business.id, page);

  if (ledger.isPending) return <Spinner />;

  if (!ledger.data || ledger.data.results.length === 0) {
    return <StateMessage icon="📒" title={t('b2b.noLedger')} body={t('b2b.noLedgerBody')} />;
  }

  return (
    <div className="business-ledger">
      <ul className="business-ledger__list">
        {ledger.data.results.map((row) => (
          <li key={row.id}>
            <div className="business-ledger__main">
              <Badge tone={KIND_TONE[row.kind] ?? 'neutral'}>
                {t(`b2b.ledgerKind.${row.kind}`, { defaultValue: row.kind })}
              </Badge>
              <span>{row.order_number ?? row.reference ?? row.note ?? '—'}</span>
            </div>

            <div className="business-ledger__side">
              <strong dir="ltr" className={row.is_debit ? 'ledger-debit' : 'ledger-credit'}>
                {row.is_debit ? '+' : '−'}
                {row.amount}
              </strong>
              <small dir="ltr">{row.occurred_on}</small>
              {/* ⚠️  الاستحقاق يظهر للفواتير وحدها: تاريخ استحقاق
                  على دفعة لا معنى له ويُقرأ خطأً. */}
              {row.due_on ? (
                <small dir="ltr">
                  {t('b2b.dueOn')} {row.due_on}
                </small>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      <Pagination page={ledger.data.page} pages={ledger.data.pages} onChange={setPage} />
    </div>
  );
}
