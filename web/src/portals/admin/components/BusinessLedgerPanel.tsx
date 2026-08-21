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
 * The business customer's account movements.
 *
 * ⚠️  **The direction is read from the sign and the colour together, not from the type.**
 *
 *     "Credit note" and "payment" both reduce the debt, and "invoice" increases
 *     it. Whoever reads the statement wants to know "up or down" before they
 *     read the movement's name — and confusing the two directions is how what
 *     we owe gets read as what we are owed.
 *
 * ⚠️  And **this statement is itemised, not aggregated**: the account statement
 *     in the credit panel gives the balances and the ageing, and this gives
 *     every movement individually — two different questions, not two versions of one.
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
              {/* ⚠️  The due date appears for invoices alone: a due date on
                  a payment is meaningless and gets misread. */}
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
