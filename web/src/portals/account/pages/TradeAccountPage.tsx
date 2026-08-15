import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMyAccount, useMyInvoices, useMyStatement } from '@/features/b2b/api';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { CreditSummary } from '../components/CreditSummary';
import { InvoiceList } from '../components/InvoiceList';
import { StatementTable } from '../components/StatementTable';

import './TradeAccountPage.css';

type Tab = 'invoices' | 'statement';

/**
 * حساب العميل التجاري.
 *
 * ⚠️  **الملخّص أولًا ثم التفاصيل.**
 *
 *     صاحب الصيدلية يفتح هذه الشاشة ليعرف رقمين: كم عليه، وكم
 *     يستطيع أن يشتري. دفنهما تحت جدول حركات يجعله يبحث عمّا
 *     جاء من أجله.
 *
 * ⚠️  والمتأخر يُعرَض في الأعلى بلا إخفاء.
 *
 *     العميل الذي يُرفض طلبه بلا أن يرى سببه يتصل بالدعم؛ والذي
 *     يرى فاتورته المتأخرة يسدّدها.
 */
export function TradeAccountPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('invoices');

  const account = useMyAccount();
  const invoices = useMyInvoices(false);
  const statement = useMyStatement({});

  if (account.isPending) return <Spinner />;

  // ⚠️  ٤٠٤ هنا ليست عطلًا: حساب تجاري لم يُفعَّل ملفه بعد.
  if (isApiError(account.error) && account.error.isNotFound) {
    return (
      <>
        <PageHeader title={t('b2b.title')} />
        <StateMessage
          icon="🏢"
          title={t('b2b.noProfile')}
          body={account.error.displayMessage}
        />
      </>
    );
  }

  if (!account.data) {
    return <StateMessage icon="⚠" title={t('state.errorTitle')} />;
  }

  return (
    <>
      <PageHeader title={t('b2b.title')} />

      {account.data.overdue_count > 0 ? (
        <Alert tone="danger">
          {t('b2b.overdueWarning', {
            count: account.data.overdue_count,
            amount: account.data.overdue_total,
          })}
        </Alert>
      ) : null}

      {!account.data.license_is_valid ? (
        <Alert tone="warning">
          {t('b2b.licenseExpired', { date: account.data.license_expires_on })}
        </Alert>
      ) : null}

      <CreditSummary account={account.data} />

      <div className="trade-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'invoices'}
          className={tab === 'invoices' ? 'is-active' : ''}
          onClick={() => setTab('invoices')}
        >
          {t('b2b.invoices')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'statement'}
          className={tab === 'statement' ? 'is-active' : ''}
          onClick={() => setTab('statement')}
        >
          {t('b2b.statement')}
        </button>
      </div>

      {tab === 'invoices' ? (
        invoices.data ? (
          <InvoiceList invoices={invoices.data.results} />
        ) : (
          <Spinner />
        )
      ) : statement.data ? (
        <StatementTable statement={statement.data} />
      ) : (
        <Spinner />
      )}
    </>
  );
}
