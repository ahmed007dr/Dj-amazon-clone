import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAccessPolicies,
  useDeleteExpenseCategory,
  useDeleteLocation,
  useDeletePolicy,
  useExpenseCategories,
  useStockLocations,
  type AccessPolicy,
  type ExpenseCategory,
  type StockLocation,
} from '@/features/settings/api';
import {
  SettingsForm,
  type SettingsKind,
} from '@/portals/admin/components/SettingsForm';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';

import './AdminSettingsPage.css';

type Row = StockLocation | ExpenseCategory | AccessPolicy;

/**
 * إعدادات مرجعية.
 *
 * ⚠️  ثلاثة نطاقات مختلفة في شاشة واحدة — والجامع بينها **متى
 *     تُضبط** لا أين تعيش: كلها تُملأ مرة عند التجهيز ثم نادرًا
 *     ما تُمسّ. تفريقها على ثلاثة مسارات يجعل التجهيز رحلة.
 */
export function AdminSettingsPage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [kind, setKind] = useState<SettingsKind>('locations');
  const [editing, setEditing] = useState<Row | null>(null);
  const [creating, setCreating] = useState(false);

  const locations = useStockLocations();
  const categories = useExpenseCategories();
  const policies = useAccessPolicies();

  const removeLocation = useDeleteLocation();
  const removeCategory = useDeleteExpenseCategory();
  const removePolicy = useDeletePolicy();

  const active =
    kind === 'locations' ? locations : kind === 'expense-categories' ? categories : policies;

  const remover =
    kind === 'locations'
      ? removeLocation
      : kind === 'expense-categories'
        ? removeCategory
        : removePolicy;

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const nameColumn: Column<Row> = {
    key: 'name',
    header: t('admin.productName'),
    render: (row) => (
      <span>
        <code style={{ direction: 'ltr' }}>{row.code}</code> — {row.name_ar}
      </span>
    ),
  };

  const statusColumn: Column<Row> = {
    key: 'status',
    header: t('admin.status'),
    render: (row) =>
      row.is_active ? (
        <Badge tone="success">{t('admin.active')}</Badge>
      ) : (
        <Badge tone="warning">{t('admin.inactive')}</Badge>
      ),
  };

  const actionsColumn: Column<Row> = {
    key: 'actions',
    header: t('admin.actions'),
    align: 'end',
    render: (row) => (
      <span className="settings-actions">
        <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>
          {t('common.edit')}
        </Button>

        {/* ⚠️  السياسة الافتراضية بلا زر حذف: حذفها يترك كل مورد
            بلا سياسة صريحة بلا مرجع — والخادم يرفض، لكن إخفاء
            الزر أوضح من رسالة رفض. */}
        {'is_default' in row && row.is_default ? null : (
          <Button
            size="sm"
            variant="ghost"
            loading={remover.isPending}
            onClick={() =>
              remover.mutate(row.id, {
                onSuccess: () => notify(t('settings.deleted'), 'success'),
                onError: fail,
              })
            }
          >
            {t('common.delete')}
          </Button>
        )}
      </span>
    ),
  };

  const columns: Column<Row>[] =
    kind === 'locations'
      ? [
          nameColumn,
          {
            key: 'kind',
            header: t('settings.locationKind'),
            secondary: true,
            render: (row) => ('kind' in row ? t(`locationKind.${row.kind}`) : '—'),
          },
          {
            key: 'sellable',
            header: t('settings.sellable'),
            secondary: true,
            // ⚠️  «يُباع منه» ليس تفصيلًا: الحجر غير قابل للبيع،
            //     وموقع مُعلَّم بالخطأ يعرض تالفًا في المتجر.
            render: (row) =>
              'is_sellable' in row && row.is_sellable ? t('common.yes') : t('common.no'),
          },
          statusColumn,
          actionsColumn,
        ]
      : kind === 'expense-categories'
        ? [
            nameColumn,
            {
              key: 'count',
              header: t('settings.expenseCount'),
              align: 'end',
              secondary: true,
              render: (row) => ('expense_count' in row ? row.expense_count : '—'),
            },
            statusColumn,
            actionsColumn,
          ]
        : [
            nameColumn,
            {
              key: 'level',
              header: t('settings.level'),
              render: (row) =>
                'level' in row ? (
                  <Badge tone={row.level === 'PUBLIC' ? 'success' : 'info'}>
                    {t(`accessLevel.${row.level}`)}
                  </Badge>
                ) : null,
            },
            {
              key: 'verified',
              header: t('settings.needsVerification'),
              secondary: true,
              render: (row) =>
                'requires_verification' in row && row.requires_verification
                  ? t('common.yes')
                  : t('common.no'),
            },
            statusColumn,
            actionsColumn,
          ];

  return (
    <>
      <PageHeader
        title={t('nav.settings')}
        description={t('settings.hint')}
        actions={<Button onClick={() => setCreating(true)}>{t(`settings.new_${kind}`)}</Button>}
      />

      <StatusTabs
        options={[
          { value: 'locations', label: t('settings.locations') },
          { value: 'expense-categories', label: t('settings.expenseCategories') },
          { value: 'policies', label: t('settings.policies') },
        ]}
        value={kind}
        onChange={(next) => {
          setKind(next as SettingsKind);
          setEditing(null);
          setCreating(false);
        }}
      />

      <DataTable
        columns={columns}
        rows={active.data ?? []}
        rowKey={(row) => row.id}
        isLoading={active.isPending}
        error={active.error}
        emptyTitle={t('settings.empty')}
        emptyBody={t(`settings.emptyBody_${kind}`)}
      />

      <Drawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        title={editing ? editing.name_ar : t(`settings.new_${kind}`)}
      >
        {creating || editing ? (
          <SettingsForm
            key={editing?.id ?? `new-${kind}`}
            kind={kind}
            {...(editing ? { row: editing } : {})}
            categories={categories.data ?? []}
            onDone={() => {
              setCreating(false);
              setEditing(null);
            }}
          />
        ) : null}
      </Drawer>
    </>
  );
}
