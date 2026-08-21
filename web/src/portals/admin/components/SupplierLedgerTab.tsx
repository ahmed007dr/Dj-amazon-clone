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
 * The supplier's movement statement — **the entire history**.
 *
 * ⚠️  It is not a duplicate of the "account statement" tab: that one is bounded
 *     by a period and gives an opening and closing balance and aggregates; this
 *     shows every movement individually, paginated. "How much do we owe them
 *     this quarter?" is a different question from "when did we last pay them?".
 *
 * ⚠️  And **the direction by colour and sign**: what we owe increases and what
 *     we paid decreases, and confusing them is how a debt we owe gets read as
 *     one owed to us.
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
              {/* ⚠️  The direction comes from `increases_debt`, not from the movement
                  type: an invoice increases what we owe and a payment reduces
                  it, and an adjustment may do either depending on its sign. */}
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
