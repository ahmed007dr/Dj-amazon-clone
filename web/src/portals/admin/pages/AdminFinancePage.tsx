import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCashFlow, useProfitAndLoss } from '@/features/finance/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { PeriodPicker } from '../components/PeriodPicker';
import { PnlStatement } from '../components/PnlStatement';

import './AdminFinancePage.css';

/**
 * The profit and loss statement.
 *
 * ⚠️  **A 403 here is not an error but the expected state for most admins.**
 *
 *     Seeing profits is an explicit permission that does not follow from
 *     entering the panel: the catalogue manager and customer service open the
 *     panel and need to know neither the margins nor the salaries. A "request
 *     the permission" message is clearer than an error screen that looks like a fault.
 */
export function AdminFinancePage() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [period, setPeriod] = useState<{ start?: string; end?: string }>({});

  const pnl = useProfitAndLoss(period);
  const flow = useCashFlow(period);

  if (isApiError(pnl.error) && pnl.error.status === 403) {
    return (
      <>
        <PageHeader title={t('finance.title')} />
        <StateMessage icon="🔒" title={t('finance.noAccess')} body={t('finance.noAccessBody')} />
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('finance.title')} />

      <PeriodPicker value={period} onChange={setPeriod} />

      {pnl.isPending ? <Spinner /> : null}

      {pnl.data ? (
        <>
          {/* ⚠️  The reliability warning goes **above the figures, not below them**.
              Goods of unknown cost make the profit higher than reality; and
              reading the figure before the warning means the decision has been taken. */}
          {!pnl.data.is_reliable ? (
            <Alert tone="warning">
              {t('finance.unreliable', { count: pnl.data.unknown_cost_units })}
            </Alert>
          ) : null}

          {Number(pnl.data.pending_expenses) > 0 ? (
            <Alert tone="info">
              {t('finance.pendingExpenses', { amount: pnl.data.pending_expenses })}
            </Alert>
          ) : null}

          <PnlStatement report={pnl.data} />

          <div className="finance-grid">
            <section className="finance-card">
              <h2>{t('finance.byCategory')}</h2>
              {pnl.data.by_category.length === 0 ? (
                <p className="finance-empty">{t('finance.noExpenses')}</p>
              ) : (
                <ul className="finance-list">
                  {pnl.data.by_category.map((row) => (
                    <li key={row.code}>
                      <span>{localized(row, 'name')}</span>
                      <strong dir="ltr">{row.total}</strong>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="finance-card">
              <h2>{t('finance.byChannel')}</h2>
              <ul className="finance-list">
                {pnl.data.by_channel.map((row) => (
                  <li key={row.channel}>
                    <span>{t(`finance.channel.${row.channel}`, { defaultValue: row.channel })}</span>
                    <strong dir="ltr">{row.total}</strong>
                  </li>
                ))}
              </ul>
            </section>

            <section className="finance-card">
              <h2>{t('finance.cashFlow')}</h2>
              {flow.data ? (
                <ul className="finance-list">
                  <li>
                    <span>{t('finance.cashIn')}</span>
                    <strong dir="ltr">{flow.data.cash_in}</strong>
                  </li>
                  <li>
                    <span>{t('finance.cashOut')}</span>
                    <strong dir="ltr">{flow.data.cash_out}</strong>
                  </li>
                  <li className="is-total">
                    <span>{t('finance.cashNet')}</span>
                    <strong dir="ltr">{flow.data.net}</strong>
                  </li>
                </ul>
              ) : (
                <Spinner />
              )}
            </section>
          </div>
        </>
      ) : null}
    </>
  );
}
