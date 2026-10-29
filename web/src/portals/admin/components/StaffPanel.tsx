import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import {
  useAdminStaff,
  useAssignCustomer,
  useResendInvite,
  useUnassignedCustomers,
  type AssignedCustomer,
  type EmployeeProfile,
} from '@/features/employees/api';
import { isApiError } from '@/shared/http/errors';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import {
  EmployeeEditForm,
  RolesPanel,
} from '@/portals/admin/components/StaffAdminPanel';
import { AssignmentsPanel } from '@/portals/admin/components/AssignmentsPanel';
import { CreateStaffForm } from '@/portals/admin/components/CreateStaffForm';
import { Drawer } from '@/shared/ui/Drawer';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { ActionMenu } from '@/shared/ui/ActionMenu';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { FilterBar, FilterSearch } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';

import './StaffPanel.css';

type Tab = 'staff' | 'unassigned' | 'roles' | 'assignments';

/**
 * Employees and customer assignment — the "staff" tab of the users-and-staff page.
 *
 * ⚠️  **"Customers with no owner" is a tab, not a buried screen.**
 *
 *     An unassigned customer is followed up by nobody and appears on no rep's
 *     dashboard — and nothing draws attention to them at all. Placing it beside
 *     the employees list makes distributing them a daily act rather than a task
 *     to be remembered.
 */
export function StaffPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('staff');
  const [editing, setEditing] = useState<EmployeeProfile | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [assignTo, setAssignTo] = useState('');

  // ⚠️  "Add staff member" is driven by `?add=1`, not by local state alone.
  //
  //     The page header's button sits above both tabs (and the old `/admin/staff?add=1`
  //     links are forwarded here), and a link can only carry a URL — so the URL is the
  //     source of truth and the button just sets it. `replace` keeps the back button
  //     from stepping through open/closed states.
  //
  //     Only `add` is touched: this page's `?tab=staff` lives in the same query string,
  //     and replacing the whole of it on close would drop the user onto the first tab.
  const [searchParams, setSearchParams] = useSearchParams();
  const creating = searchParams.get('add') === '1';
  const setCreating = (open: boolean) =>
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (open) next.set('add', '1');
        else next.delete('add');
        return next;
      },
      { replace: true },
    );

  const resendInvite = useResendInvite();

  const debounced = useDebounced(search);
  const staff = useAdminStaff({ ...(debounced ? { search: debounced } : {}), page });
  const unassigned = useUnassignedCustomers(page);
  const assign = useAssignCustomer();

  if (isApiError(staff.error) && staff.error.status === 403) {
    return <StateMessage icon="🔒" title={t('staff.noAccess')} body={t('staff.noAccessBody')} />;
  }

  const staffColumns: Column<EmployeeProfile>[] = [
    {
      key: 'name',
      header: t('staff.employee'),
      render: (row) => (
        <div className="staff-cell">
          <strong>{row.full_name}</strong>
          <code>{row.employee_number}</code>
        </div>
      ),
    },
    {
      key: 'role',
      header: t('staff.role'),
      render: (row) => (
        <div className="staff-cell">
          <span>{localized(row, 'role_name')}</span>
          {/* ⚠️  The door, shown beside the role: a person who can open the admin
              panel is a different decision from one who can only reach /staff. */}
          {row.account_type === 'ADMIN' ? (
            <Badge tone="info">{t('staff.access.ADMIN_PANEL')}</Badge>
          ) : null}
        </div>
      ),
    },
    {
      key: 'manager',
      header: t('staff.manager'),
      secondary: true,
      render: (row) => row.manager_name ?? '—',
    },
    {
      key: 'customers',
      header: t('staff.customersCount'),
      align: 'end',
      render: (row) => row.customers_count,
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) =>
        row.is_active ? (
          <span className="staff-cell">
            <Badge tone="success">{t('staff.onDuty')}</Badge>
            {/* Invited but has not signed in yet — the link (or temporary password) is unused. */}
            {row.invite_pending ? <Badge tone="warning">{t('staff.invitePending')}</Badge> : null}
          </span>
        ) : (
          // ⚠️  A deactivated employee appears in the list and is not hidden: hiding them
          //     makes their customers look unassigned with no explanation.
          <Badge tone="danger">{t('staff.offDuty')}</Badge>
        ),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <ActionMenu
          menuLabel={`${t('admin.actions')} · ${row.full_name}`}
          items={[
            // ⚠️  Only while the invite is unused: the server refuses it afterwards
            //     (an active person uses "forgot password"), so offering it would be an
            //     item that always fails. It is disabled, not hidden, while this row's
            //     resend is in flight — a second press would send a second email.
            {
              key: 'resend-invite',
              label: t('staff.resendInvite'),
              hidden: !(row.is_active && row.invite_pending),
              disabled: resendInvite.isPending && resendInvite.variables === row.id,
              onSelect: () =>
                resendInvite.mutate(row.id, {
                  onSuccess: () => notify(t('staff.inviteResent', { email: row.email }), 'success'),
                  onError: (error) =>
                    notify(
                      isApiError(error) ? error.displayMessage : t('state.errorTitle'),
                      'danger',
                    ),
                }),
            },
            {
              key: 'edit',
              label: t('common.edit'),
              onSelect: () => setEditing(row),
            },
          ]}
        />
      ),
    },
  ];

  const unassignedColumns: Column<AssignedCustomer>[] = [
    {
      key: 'name',
      header: t('staff.customer'),
      render: (row) => (
        <div className="staff-cell">
          <strong>{row.display_name}</strong>
          <code>{row.customer_number}</code>
        </div>
      ),
    },
    {
      key: 'spent',
      header: t('staff.totalSpent'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.total_spent}</span>,
    },
    {
      key: 'orders',
      header: t('staff.ordersCount'),
      align: 'end',
      secondary: true,
      render: (row) => row.total_orders,
    },
    {
      key: 'assign',
      header: '',
      align: 'end',
      render: (row) => (
        <Button
          size="sm"
          disabled={assignTo === '' || assign.isPending}
          onClick={() =>
            assign.mutate(
              { customer: row.id, employee: assignTo },
              {
                onSuccess: () => notify(t('staff.assigned'), 'success'),
                onError: (error) =>
                  notify(
                    isApiError(error) ? error.displayMessage : t('state.errorTitle'),
                    'danger',
                  ),
              },
            )
          }
        >
          {t('staff.assign')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <div className="staff-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'staff'}
          className={tab === 'staff' ? 'is-active' : ''}
          onClick={() => {
            setTab('staff');
            setPage(1);
          }}
        >
          {/* ⚠️  "Staff list", not "Staff": the page's own tab above is already called
              "Staff", and two bars both saying it read as one tab repeated. */}
          {t('staff.listTab')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'unassigned'}
          className={tab === 'unassigned' ? 'is-active' : ''}
          onClick={() => {
            setTab('unassigned');
            setPage(1);
          }}
        >
          {t('staff.unassigned')}
          {unassigned.data && unassigned.data.count > 0 ? (
            <span className="staff-tabs__count">{unassigned.data.count}</span>
          ) : null}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'roles'}
          className={tab === 'roles' ? 'is-active' : ''}
          onClick={() => setTab('roles')}
        >
          {t('staff.roles')}
        </button>
        {/* ⚠️  The assignment log beside the employees: whoever reviews a commission
            reviews who was serving the customer at the time — and they are
            practically one screen. */}
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'assignments'}
          className={tab === 'assignments' ? 'is-active' : ''}
          onClick={() => {
            setTab('assignments');
            setPage(1);
          }}
        >
          {t('staff.assignments')}
        </button>
      </div>

      {tab === 'roles' ? <RolesPanel /> : null}
      {tab === 'assignments' ? <AssignmentsPanel /> : null}

      {tab === 'staff' ? (
        <>
          <FilterBar>
            <FilterSearch
              value={search}
              onChange={(value) => {
                setSearch(value);
                setPage(1);
              }}
              placeholder={t('staff.searchStaff')}
            />
          </FilterBar>

          <DataTable
            columns={staffColumns}
            rows={staff.data?.results ?? []}
            isLoading={staff.isPending}
            error={staff.error}
            rowKey={(row) => row.id}
            emptyTitle={t('staff.noStaff')}
          />

          {staff.data ? (
            <Pagination page={staff.data.page} pages={staff.data.pages} onChange={setPage} />
          ) : null}
        </>
      ) : (
        <>
          {/* ⚠️  Choosing the employee **before** the table rather than in every row.
              Putting a dropdown in each row makes distributing twenty customers
              twenty repeated selections of the same rep. */}
          <label className="staff-assign-picker">
            {t('staff.assignTo')}
            <select value={assignTo} onChange={(event) => setAssignTo(event.target.value)}>
              <option value="">{t('common.choose')}</option>
              {(staff.data?.results ?? [])
                .filter((row) => row.is_active)
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.full_name} · {row.employee_number}
                  </option>
                ))}
            </select>
          </label>

          {assignTo === '' ? (
            <Alert tone="info">{t('staff.pickEmployeeFirst')}</Alert>
          ) : null}

          <DataTable
            columns={unassignedColumns}
            rows={unassigned.data?.results ?? []}
            isLoading={unassigned.isPending}
            error={unassigned.error}
            rowKey={(row) => row.id}
            emptyTitle={t('staff.allAssigned')}
          />

          {unassigned.data ? (
            <Pagination
              page={unassigned.data.page}
              pages={unassigned.data.pages}
              onChange={setPage}
            />
          ) : null}
        </>
      )}

      <Drawer open={creating} onClose={() => setCreating(false)} title={t('staff.addStaff')}>
        {/* ⚠️  Mounted only while open, so a cancelled draft is not remembered and a
            second "add" starts from an empty form. */}
        {creating ? <CreateStaffForm onDone={() => setCreating(false)} /> : null}
      </Drawer>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.full_name ?? ''}
      >
        {editing ? (
          <EmployeeEditForm
            key={editing.id}
            employee={editing}
            onDone={() => setEditing(null)}
          />
        ) : null}
      </Drawer>
    </>
  );
}
