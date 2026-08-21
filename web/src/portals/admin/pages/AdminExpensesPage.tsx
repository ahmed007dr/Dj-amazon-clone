import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useExpenseDecision,
  useExpenses,
  type Expense,
} from '@/features/finance/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterBar, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate } from '@/shared/utils/format';
import { useToast } from '@/shared/ui/useToast';

import { ExpenseForm } from '../components/ExpenseForm';

import './AdminExpensesPage.css';

const TONE: Record<string, 'info' | 'success' | 'danger'> = {
  DRAFT: 'info',
  APPROVED: 'success',
  REJECTED: 'danger',
};

/**
 * Expenses.
 *
 * ⚠️  **The default tab is "draft", not "all".**
 *
 *     Whoever opens this screen opens it to settle what is waiting; and an "all"
 *     list buries the three new ones under two hundred approved.
 */
export function AdminExpensesPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [status, setStatus] = useState('DRAFT');
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  const query = useExpenses({ ...(status ? { status } : {}), page });
  const decide = useExpenseDecision();

  const act = (expense: Expense, decision: 'APPROVE' | 'REJECT') => {
    // ⚠️  The rejection reason is mandatory on the server — it is requested here
    //     before submitting, so a 400 does not come back after a press with no explanation.
    const reason =
      decision === 'REJECT' ? window.prompt(t('finance.rejectReason')) ?? '' : undefined;

    if (decision === 'REJECT' && !reason?.trim()) return;

    decide.mutate(
      { id: expense.id, decision, ...(reason ? { reason } : {}) },
      {
        onError: (error) =>
          notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  if (isApiError(query.error) && query.error.status === 403) {
    return (
      <>
        <PageHeader title={t('finance.expensesTitle')} />
        <StateMessage icon="🔒" title={t('finance.noAccess')} body={t('finance.noAccessBody')} />
      </>
    );
  }

  const columns: Column<Expense>[] = [
    {
      key: 'date',
      header: t('finance.incurredOn'),
      render: (row) => formatDate(row.incurred_on, i18n.language),
    },
    {
      key: 'category',
      header: t('finance.category'),
      render: (row) => localized(row, 'category_name'),
    },
    {
      key: 'vendor',
      header: t('finance.vendor'),
      secondary: true,
      render: (row) => row.vendor_name || '—',
    },
    {
      key: 'amount',
      header: t('finance.amount'),
      align: 'end',
      render: (row) => <strong dir="ltr">{row.amount}</strong>,
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={TONE[row.status] ?? 'info'}>{t(`finance.status.${row.status}`)}</Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) =>
        // ⚠️  The decision buttons appear for drafts alone.
        //
        //     Showing them for an approved one invites a press that returns 409 — and
        //     an approved expense is not edited because it has entered a report already issued.
        row.status === 'DRAFT' ? (
          <div className="expense-actions">
            <Button size="sm" loading={decide.isPending} onClick={() => act(row, 'APPROVE')}>
              {t('finance.approve')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => act(row, 'REJECT')}>
              {t('finance.reject')}
            </Button>
          </div>
        ) : (
          <span className="expense-decided">{row.approved_by_email ?? '—'}</span>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('finance.expensesTitle')}
        actions={<Button onClick={() => setCreating(true)}>{t("finance.addExpense")}</Button>}
      />

      <FilterBar>
        <FilterSelect
          label={t('admin.all')}
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={[
            { value: 'DRAFT', label: t('finance.status.DRAFT') },
            { value: 'APPROVED', label: t('finance.status.APPROVED') },
            { value: 'REJECTED', label: t('finance.status.REJECTED') },
          ]}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(row) => row.id}
        emptyTitle={t('finance.noExpenses')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Drawer
        open={creating}
        onClose={() => setCreating(false)}
        title={t('finance.addExpense')}
      >
        {creating ? <ExpenseForm onDone={() => setCreating(false)} /> : null}
      </Drawer>
    </>
  );
}
