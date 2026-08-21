import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useActivateTarget,
  useAdminCommissions,
  useAdminTargets,
  useCalculateCommissions,
  useCloseTarget,
  useCommissionDecision,
  type CommissionRecord,
  type MonthlyTarget,
} from '@/features/targets/api';
import { isApiError } from '@/shared/http/errors';
import { CommissionExplainDrawer } from '@/portals/admin/components/CommissionExplainDrawer';
import {
  BulkTargetsForm,
  SchemesPanel,
  TargetEditForm,
} from '@/portals/admin/components/TargetsAdminPanel';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Drawer } from '@/shared/ui/Drawer';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';

import './AdminTargetsPage.css';

type Tab = 'targets' | 'commissions' | 'schemes';

const TARGET_TONE: Record<string, 'info' | 'success' | 'neutral'> = {
  DRAFT: 'info',
  ACTIVE: 'success',
  CLOSED: 'neutral',
};

const COMMISSION_TONE: Record<string, 'info' | 'success' | 'danger' | 'neutral'> = {
  CALCULATED: 'info',
  APPROVED: 'success',
  PAID: 'success',
  REJECTED: 'danger',
};

/**
 * Targets and commissions.
 *
 * ⚠️  **The month is chosen once and governs both tabs.**
 *
 *     The target and the commission are two faces of the same month; choosing
 *     an independent period per tab makes the admin read July's commission
 *     beside August's target without noticing.
 */
export function AdminTargetsPage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const today = new Date();
  const [tab, setTab] = useState<Tab>('targets');
  const [editingTarget, setEditingTarget] = useState<MonthlyTarget | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [page, setPage] = useState(1);
  const [explaining, setExplaining] = useState<CommissionRecord | null>(null);

  const targets = useAdminTargets({ year, month, page });
  const commissions = useAdminCommissions({ year, month, page });

  const activate = useActivateTarget();
  const close = useCloseTarget();
  const calculate = useCalculateCommissions();
  const decide = useCommissionDecision();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  if (isApiError(targets.error) && targets.error.status === 403) {
    return (
      <>
        <PageHeader title={t('targets.title')} />
        <StateMessage icon="🔒" title={t('staff.noAccess')} body={t('staff.noAccessBody')} />
      </>
    );
  }

  const targetColumns: Column<MonthlyTarget>[] = [
    {
      key: 'employee',
      header: t('staff.employee'),
      render: (row) => (
        <div className="target-cell">
          <strong>{row.employee_name}</strong>
          <code>{row.employee_number}</code>
        </div>
      ),
    },
    {
      key: 'type',
      header: t('targets.type'),
      secondary: true,
      render: (row) => t(`targets.targetType.${row.target_type}`, { defaultValue: row.target_type }),
    },
    {
      key: 'value',
      header: t('targets.target'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.target_value}</span>,
    },
    {
      key: 'minimum',
      header: t('targets.minimum'),
      align: 'end',
      secondary: true,
      render: (row) => <span dir="ltr">{row.minimum_achievement_percent}%</span>,
    },
    {
      key: 'achieved',
      header: t('targets.achieved'),
      align: 'end',
      // ⚠️  The achievement appears **for closed ones alone**: before closing it is a
      //     live figure that changes, and showing it in a static table makes it look final.
      render: (row) =>
        row.achievement_percent !== null ? (
          <span dir="ltr">{row.achievement_percent}%</span>
        ) : (
          <span className="target-live">{t('targets.live')}</span>
        ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={TARGET_TONE[row.status] ?? 'neutral'}>
          {t(`targets.status.${row.status}`)}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <div className="target-actions">
          {row.status === 'DRAFT' ? (
            <Button
              size="sm"
              loading={activate.isPending}
              onClick={() => activate.mutate(row.id, { onError: fail })}
            >
              {t('targets.activate')}
            </Button>
          ) : null}
          {row.status === 'ACTIVE' ? (
            <Button
              size="sm"
              variant="ghost"
              loading={close.isPending}
              onClick={() => close.mutate(row.id, { onError: fail })}
            >
              {t('targets.close')}
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  const commissionColumns: Column<CommissionRecord>[] = [
    {
      key: 'employee',
      header: t('staff.employee'),
      render: (row) => (
        <div className="target-cell">
          <strong>{row.employee_name}</strong>
          <code>{row.employee_number}</code>
        </div>
      ),
    },
    {
      key: 'achievement',
      header: t('targets.achievement'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.achievement_percent}%</span>,
    },
    {
      key: 'tier',
      header: t('targets.tier'),
      secondary: true,
      render: (row) => <span className="target-tier">{row.tier_label}</span>,
    },
    {
      key: 'base',
      header: t('targets.baseAmount'),
      align: 'end',
      secondary: true,
      render: (row) => <span dir="ltr">{row.base_amount}</span>,
    },
    {
      key: 'amount',
      header: t('targets.commission'),
      align: 'end',
      render: (row) => (
        <strong dir="ltr" className="target-amount">
          {row.amount}
        </strong>
      ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={COMMISSION_TONE[row.status] ?? 'neutral'}>
          {t(`targets.commissionStatus.${row.status}`)}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <div className="target-actions">
          {/* ⚠️  "Why?" first in the row: "why is my commission 420 and not 600?"
              is asked before approval, not after — and approving with no
              explanation is how a wrong figure gets paid. */}
          <Button size="sm" variant="ghost" onClick={() => setExplaining(row)}>
            {t('targets.why')}
          </Button>

          {/* ⚠️  "Pay" appears only after approval: skipping it bypasses the
              review — the one step that catches a calculation error before
              the money leaves. */}
          {row.status === 'CALCULATED' ? (
            <Button
              size="sm"
              loading={decide.isPending}
              onClick={() =>
                decide.mutate({ id: row.id, decision: 'APPROVE' }, { onError: fail })
              }
            >
              {t('targets.approve')}
            </Button>
          ) : null}
          {row.status === 'APPROVED' ? (
            <Button
              size="sm"
              variant="secondary"
              loading={decide.isPending}
              onClick={() => decide.mutate({ id: row.id, decision: 'PAY' }, { onError: fail })}
            >
              {t('targets.pay')}
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('targets.title')}
        actions={<Button onClick={() => setBulkOpen(true)}>{t('targets.bulkTitle')}</Button>}
      />

      <div className="target-period">
        <label>
          {t('targets.year')}
          <input
            type="number"
            min="2020"
            max="2100"
            dir="ltr"
            value={year}
            onChange={(event) => {
              setYear(Number(event.target.value) || today.getFullYear());
              setPage(1);
            }}
          />
        </label>
        <label>
          {t('targets.month')}
          <input
            type="number"
            min="1"
            max="12"
            dir="ltr"
            value={month}
            onChange={(event) => {
              setMonth(Number(event.target.value) || 1);
              setPage(1);
            }}
          />
        </label>

        <Button
          variant="secondary"
          loading={calculate.isPending}
          onClick={() =>
            calculate.mutate(
              { year, month },
              {
                onSuccess: (result) =>
                  notify(
                    t('targets.calculated', {
                      count: result.calculated,
                      skipped: result.skipped.length,
                    }),
                    result.skipped.length > 0 ? 'info' : 'success',
                  ),
                onError: fail,
              },
            )
          }
        >
          {t('targets.calculate')}
        </Button>
      </div>

      {/* ⚠️  Those skipped are shown by name with their reasons — not merely "done".
          An employee with no commission scheme stays without one silently if only a count is given. */}
      {calculate.data && calculate.data.skipped.length > 0 ? (
        <Alert tone="warning">
          {t('targets.skipped')}
          <ul className="target-skipped">
            {calculate.data.skipped.map((row) => (
              <li key={row.employee}>
                <code>{row.employee}</code> — {row.reason}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <div className="target-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'targets'}
          className={tab === 'targets' ? 'is-active' : ''}
          onClick={() => setTab('targets')}
        >
          {t('targets.targetsTab')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'commissions'}
          className={tab === 'commissions' ? 'is-active' : ''}
          onClick={() => setTab('commissions')}
        >
          {t('targets.commissionsTab')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'schemes'}
          className={tab === 'schemes' ? 'is-active' : ''}
          onClick={() => setTab('schemes')}
        >
          {t('targets.schemesTab')}
        </button>
      </div>

      {tab === 'schemes' ? <SchemesPanel /> : null}

      {tab === 'targets' ? (
        <>
          <DataTable
            columns={targetColumns}
            rows={targets.data?.results ?? []}
            isLoading={targets.isPending}
            error={targets.error}
            rowKey={(row) => row.id}
            emptyTitle={t('targets.noTargets')}
          />
          {targets.data ? (
            <Pagination page={targets.data.page} pages={targets.data.pages} onChange={setPage} />
          ) : null}
        </>
      ) : (
        <>
          <DataTable
            columns={commissionColumns}
            rows={commissions.data?.results ?? []}
            isLoading={commissions.isPending}
            error={commissions.error}
            rowKey={(row) => row.id}
            emptyTitle={t('targets.noCommissions')}
            emptyBody={t('targets.noCommissionsBody')}
          />
          {commissions.data ? (
            <Pagination
              page={commissions.data.page}
              pages={commissions.data.pages}
              onChange={setPage}
            />
          ) : null}
        </>
      )}

      <Drawer
        open={bulkOpen || editingTarget !== null}
        onClose={() => {
          setBulkOpen(false);
          setEditingTarget(null);
        }}
        title={editingTarget ? t('targets.editTarget') : t('targets.bulkTitle')}
      >
        {editingTarget ? (
          <TargetEditForm
            key={editingTarget.id}
            target={editingTarget}
            onDone={() => setEditingTarget(null)}
          />
        ) : bulkOpen ? (
          <BulkTargetsForm year={year} month={month} onDone={() => setBulkOpen(false)} />
        ) : null}
      </Drawer>

      <CommissionExplainDrawer record={explaining} onClose={() => setExplaining(null)} />
    </>
  );
}
