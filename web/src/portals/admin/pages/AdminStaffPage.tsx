import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdminStaff,
  useAssignCustomer,
  useUnassignedCustomers,
  type AssignedCustomer,
  type EmployeeProfile,
} from '@/features/employees/api';
import { isApiError } from '@/shared/http/errors';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { FilterBar, FilterSearch } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';

import './AdminStaffPage.css';

type Tab = 'staff' | 'unassigned';

/**
 * الموظفون وإسناد العملاء.
 *
 * ⚠️  **«عملاء بلا مسؤول» تبويب لا شاشة مدفونة.**
 *
 *     عميل بلا إسناد لا يتابعه أحد ولا يظهر في لوحة أي مندوب —
 *     ولا شيء ينبّه إليه إطلاقًا. وضعه بجوار قائمة الموظفين
 *     يجعل توزيعه فعلًا يوميًا لا مهمة تُتذكَّر.
 */
export function AdminStaffPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('staff');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [assignTo, setAssignTo] = useState('');

  const debounced = useDebounced(search);
  const staff = useAdminStaff({ ...(debounced ? { search: debounced } : {}), page });
  const unassigned = useUnassignedCustomers(page);
  const assign = useAssignCustomer();

  if (isApiError(staff.error) && staff.error.status === 403) {
    return (
      <>
        <PageHeader title={t('staff.staffTitle')} />
        <StateMessage icon="🔒" title={t('staff.noAccess')} body={t('staff.noAccessBody')} />
      </>
    );
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
      render: (row) => localized(row, 'role_name'),
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
          <Badge tone="success">{t('staff.onDuty')}</Badge>
        ) : (
          // ⚠️  الموقوف يظهر في القائمة ولا يُخفى: إخفاؤه يجعل
          //     عملاءه يبدون بلا مسؤول بلا تفسير.
          <Badge tone="danger">{t('staff.offDuty')}</Badge>
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
      <PageHeader title={t('staff.staffTitle')} />

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
          {t('staff.staffTitle')}
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
      </div>

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
          {/* ⚠️  اختيار الموظف **قبل** الجدول لا في كل صف.
              وضع قائمة منسدلة في كل صف يجعل توزيع عشرين عميلًا
              عشرين اختيارًا متكررًا لنفس المندوب. */}
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
    </>
  );
}
