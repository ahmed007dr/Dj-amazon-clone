import { useTranslation } from 'react-i18next';

import { useAdminCommissionExplain, type CommissionRecord } from '@/features/targets/api';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';

import './CommissionExplainDrawer.css';

/** A deliberate order: from revenue to profit to the tier to the amount. */
const ORDER = [
  'employee',
  'period',
  'orders_count',
  'gross_sales',
  'returns',
  'net_sales',
  'cost',
  'gross_profit',
  'target',
  'achieved',
  'achievement_percent',
  'scheme',
  'base',
  'base_amount',
  'tier',
  'rate',
  'amount',
];

/**
 * The commission explanation.
 *
 * ⚠️  **A commission is a figure that gets paid — and a figure that cannot be explained does not get paid.**
 *
 *     "Why is my commission 420 and not 600?" is a question every rep asks in
 *     the first month. Without this panel the accountant opens the source or
 *     guesses, and both produce an answer that cannot be proved.
 *
 * ⚠️  And **the lines follow the derivation order, not the alphabet**: sales,
 *     then returns, then net, then cost, then profit — each line derived from
 *     the one above it, so the reader follows the calculation instead of
 *     jumping around in it.
 */
export function CommissionExplainDrawer({
  record,
  onClose,
}: {
  record: CommissionRecord | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const explain = useAdminCommissionExplain(record?.id ?? null);

  return (
    <Drawer
      open={record !== null}
      onClose={onClose}
      {...(record ? { title: record.employee_name } : {})}
    >
      {explain.isPending ? (
        <Spinner />
      ) : explain.data ? (
        <dl className="commission-explain">
          {ORDER.filter((key) => explain.data[key] !== undefined).map((key) => (
            <div key={key} className={key === 'amount' ? 'is-total' : ''}>
              <dt>{t(`targets.explainRow.${key}`, { defaultValue: key })}</dt>
              <dd dir="ltr">{String(explain.data[key])}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </Drawer>
  );
}
