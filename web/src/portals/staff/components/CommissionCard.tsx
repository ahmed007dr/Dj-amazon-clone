import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCommissionExplain, type CommissionRecord } from '@/features/targets/api';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';

import './CommissionCard.css';

const TONE: Record<string, 'info' | 'success' | 'danger' | 'neutral'> = {
  CALCULATED: 'info',
  APPROVED: 'success',
  PAID: 'success',
  REJECTED: 'danger',
};

/**
 * A month's commission card.
 *
 * ⚠️  **The "how was this calculated?" button is not decoration.**
 *
 *     The rep reads an amount that will be paid to them. With no explanation
 *     they compare it against their own estimate and call accounting on every
 *     difference — and a difference is normal, because returns, the floor and
 *     the tiers are not computed in one's head.
 *
 * ⚠️  And the explanation comes **from the record**, not from a recomputation.
 *
 *     The numbers are stored at the moment of calculation; recomputing them when
 *     the screen opens gives an answer that changes from one day to the next
 *     about an amount that has not changed.
 */
export function CommissionCard({ record }: { record: CommissionRecord }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const explain = useCommissionExplain(open ? record.id : null);

  return (
    <article className="commission-card">
      <header>
        <span className="commission-card__period" dir="ltr">
          {record.year}-{String(record.month).padStart(2, '0')}
        </span>
        <Badge tone={TONE[record.status] ?? 'neutral'}>
          {t(`targets.commissionStatus.${record.status}`)}
        </Badge>
      </header>

      <strong className="commission-card__amount" dir="ltr">
        {record.amount}
      </strong>

      <p className="commission-card__summary">
        {t('targets.rateOn', {
          rate: record.rate,
          base: t(`targets.base.${record.base}`),
          amount: record.base_amount,
        })}
      </p>

      <Button size="sm" variant="ghost" onClick={() => setOpen((value) => !value)}>
        {open ? t('targets.hideExplain') : t('targets.explain')}
      </Button>

      {open ? (
        explain.isPending ? (
          <Spinner />
        ) : explain.data ? (
          <dl className="commission-card__explain">
            <dt>{t('targets.ordersCount')}</dt>
            <dd dir="ltr">{explain.data.orders_count}</dd>
            <dt>{t('targets.gross')}</dt>
            <dd dir="ltr">{explain.data.gross_sales}</dd>
            <dt>{t('targets.returns')}</dt>
            <dd dir="ltr">−{explain.data.returns}</dd>
            <dt>{t('targets.net')}</dt>
            <dd dir="ltr">{explain.data.net_sales}</dd>
            <dt>{t('targets.cost')}</dt>
            <dd dir="ltr">{explain.data.cost}</dd>
            <dt>{t('targets.profit')}</dt>
            <dd dir="ltr">{explain.data.gross_profit}</dd>
            <dt>{t('targets.target')}</dt>
            <dd dir="ltr">{explain.data.target}</dd>
            <dt>{t('targets.achievement')}</dt>
            <dd dir="ltr">{explain.data.achievement_percent}%</dd>
            <dt>{t('targets.tier')}</dt>
            <dd>{explain.data.tier}</dd>
            <dt>{t('targets.rate')}</dt>
            <dd dir="ltr">{explain.data.rate}%</dd>
          </dl>
        ) : null
      ) : null}
    </article>
  );
}
