import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSupplierLedger } from '@/features/suppliers/api';
import { Badge } from '@/shared/ui/Badge';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './SupplierPanel.css';

const KIND_TONE: Record<string, 'danger' | 'success' | 'info' | 'neutral'> = {
  INVOICE: 'danger',
  PAYMENT: 'success',
  CREDIT_NOTE: 'info',
  ADJUSTMENT: 'neutral',
};

/**
 * كشف حركات المورّد — **كل التاريخ**.
 *
 * ⚠️  ليس تكرارًا لتبويب «كشف الحساب»: ذاك مقيَّد بفترة ويعطي
 *     رصيدًا افتتاحيًا وختاميًا وتجميعات؛ وهذا يعرض كل حركة على
 *     حدة مرقَّمة. سؤال «كم عليه في الربع الأخير؟» غير سؤال
 *     «متى دفعنا له آخر مرة؟».
 *
 * ⚠️  و**الاتجاه بلون وإشارة**: ما علينا يزيد وما دفعناه ينقص،
 *     وخلطهما هو كيف يُقرأ دَينٌ علينا كأنه لنا.
 */
export function SupplierLedgerTab({ supplier }: { supplier: string }) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const ledger = useSupplierLedger(supplier, page);

  if (ledger.isPending) return <Spinner />;

  if (!ledger.data || ledger.data.results.length === 0) {
    return <StateMessage icon="📒" title={t('suppliers.noLedger')} />;
  }

  return (
    <div className="supplier-ledger">
      <ul className="supplier-ledger__list">
        {ledger.data.results.map((entry) => (
          <li key={entry.id}>
            <div className="supplier-ledger__main">
              <Badge tone={KIND_TONE[entry.kind] ?? 'neutral'}>
                {t(`suppliers.ledgerKind.${entry.kind}`, { defaultValue: entry.kind })}
              </Badge>
              <span>{entry.reference || entry.note || '—'}</span>
            </div>

            <div className="supplier-ledger__side">
              {/* ⚠️  الاتجاه من `increases_debt` لا من نوع الحركة:
                  الفاتورة تزيد ما علينا والدفعة تنقصه، والتسوية
                  قد تفعل الاثنين حسب إشارتها. */}
              <strong
                dir="ltr"
                className={entry.increases_debt ? 'ledger-debit' : 'ledger-credit'}
              >
                {entry.increases_debt ? '+' : '−'}
                {entry.amount}
              </strong>
              <small dir="ltr">{entry.occurred_on}</small>
            </div>
          </li>
        ))}
      </ul>

      <Pagination page={ledger.data.page} pages={ledger.data.pages} onChange={setPage} />
    </div>
  );
}
