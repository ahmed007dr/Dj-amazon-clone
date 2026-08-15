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
 * بطاقة عمولة شهر.
 *
 * ⚠️  **زر «كيف حُسبت؟» ليس زينة.**
 *
 *     المندوب يقرأ مبلغًا سيُصرَف له. بلا تفسير يقارنه بتقديره
 *     الخاص ويتصل بالمحاسبة عند كل فرق — والفرق طبيعي لأن
 *     المرتجعات والحد الأدنى والشرائح لا تُحسب في الرأس.
 *
 * ⚠️  والتفسير يأتي **من السجل** لا بإعادة حساب.
 *
 *     الأرقام مخزَّنة لحظة الحساب؛ فإعادة حسابها عند فتح الشاشة
 *     تعطي جوابًا يتغيّر بين يوم وآخر عن مبلغ لم يتغيّر.
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
