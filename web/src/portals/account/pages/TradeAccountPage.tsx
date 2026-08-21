import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMyAccount, useMyInvoices, useMyStatement } from '@/features/b2b/api';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { BusinessProfileForm } from '@/portals/account/components/BusinessProfileForm';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { CreditSummary } from '../components/CreditSummary';
import { InvoiceList } from '../components/InvoiceList';
import { StatementTable } from '../components/StatementTable';

import './TradeAccountPage.css';

type Tab = 'invoices' | 'statement' | 'details';

/**
 * The business customer's account.
 *
 * ⚠️  **The summary first, then the details.**
 *
 *     A pharmacy owner opens this screen to learn two figures: how much they
 *     owe, and how much they can buy. Burying them under a movements table
 *     makes them hunt for what they came for.
 *
 * ⚠️  And overdue amounts are shown at the top, unhidden.
 *
 *     A customer whose order is refused without seeing why calls support; one
 *     who sees their overdue invoice pays it.
 */
export function TradeAccountPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('invoices');

  const account = useMyAccount();
  const invoices = useMyInvoices(false);
  const statement = useMyStatement({});

  if (account.isPending) return <Spinner />;

  // ⚠️  A 404 here is not a fault: a business account whose profile is not yet activated.
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
        {/* ⚠️  "My details" is a tab rather than a separate screen: it is opened to
            renew an expired licence, and the expiry warning appears directly
            above these tabs — so the distance between the warning and its
            remedy is one step. */}
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'details'}
          className={tab === 'details' ? 'is-active' : ''}
          onClick={() => setTab('details')}
        >
          {t('b2b.myDetails')}
        </button>
      </div>

      {tab === 'details' ? (
        <BusinessProfileForm />
      ) : tab === 'invoices' ? (
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
