import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useBrands,
  useCategories,
  useDeleteReference,
  useManufacturers,
  type AdminBrand,
  type AdminCategory,
  type AdminManufacturer,
  type ReferenceKind,
} from '@/features/catalog/referenceApi';
import { ReferenceForm } from '@/portals/admin/components/ReferenceForm';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Modal } from '@/shared/ui/Modal';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';

import './AdminReferencePage.css';

type Row = AdminCategory | AdminBrand | AdminManufacturer;

/**
 * Reference classification.
 *
 * ⚠️  **One screen with three tabs, not three screens.**
 *
 *     All three are configured in a single session at setup: the company is
 *     created, then its brand, then the category is assigned. Splitting them
 *     across three routes makes every step lose the context of the one before it.
 *
 * ⚠️  And **categories first**: they are the mandatory one on a product, and the
 *     rest are optional.
 */
export function AdminReferencePage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [kind, setKind] = useState<ReferenceKind>('categories');
  const [editing, setEditing] = useState<Row | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Row | null>(null);

  const categories = useCategories(kind === 'categories');
  const brands = useBrands(kind === 'brands');
  const manufacturers = useManufacturers(kind === 'manufacturers');
  // Categories are always needed in the category form itself (choosing the parent)
  const allCategories = useCategories();
  const allManufacturers = useManufacturers();

  const remove = useDeleteReference(kind);

  const active =
    kind === 'categories' ? categories : kind === 'brands' ? brands : manufacturers;

  const confirmDelete = () => {
    if (!pendingDelete) return;
    remove.mutate(pendingDelete.id, {
      onSuccess: () => {
        notify(t('reference.deleted'), 'success');
        setPendingDelete(null);
      },
      onError: (error) => {
        // ⚠️  The server's message is shown as it is: it is what counts what blocks the
        //     deletion ("this category has 12 products") — and a generic message loses that.
        notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');
        setPendingDelete(null);
      },
    });
  };

  const nameColumn: Column<Row> = {
    key: 'name',
    header: t('admin.productName'),
    render: (row) =>
      'path_label' in row ? (
        // ⚠️  Indenting by depth makes the flat list read as a tree —
        //     "Tablets" alone is ambiguous under both "Medicines" and "Supplements".
        <span style={{ paddingInlineStart: `${row.depth * 1.25}rem` }}>
          {row.depth > 0 ? <span className="ref-branch" aria-hidden>└ </span> : null}
          {row.name_ar}
        </span>
      ) : (
        row.name_ar
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

  const usageColumn: Column<Row> = {
    key: 'usage',
    header: t('reference.usage'),
    align: 'end',
    secondary: true,
    // ⚠️  The count is visible **before** pressing delete: seeing it turns the
    //     decision from a guess into knowledge, rather than a refusal message after the attempt.
    render: (row) =>
      'product_count' in row
        ? t('reference.products', { count: row.product_count })
        : 'brand_count' in row
          ? t('reference.brands', { count: row.brand_count })
          : '—',
  };

  const actionsColumn: Column<Row> = {
    key: 'actions',
    header: t('admin.actions'),
    align: 'end',
    render: (row) => (
      <span className="ref-actions">
        <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>
          {t('common.edit')}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setPendingDelete(row)}>
          {t('common.delete')}
        </Button>
      </span>
    ),
  };

  const columns: Column<Row>[] =
    kind === 'brands'
      ? [
          nameColumn,
          {
            key: 'maker',
            header: t('catalog.manufacturer'),
            secondary: true,
            render: (row) => ('manufacturer_name' in row ? row.manufacturer_name || '—' : '—'),
          },
          statusColumn,
          usageColumn,
          actionsColumn,
        ]
      : kind === 'manufacturers'
        ? [
            nameColumn,
            {
              key: 'country',
              header: t('reference.country'),
              secondary: true,
              render: (row) => ('country' in row ? row.country || '—' : '—'),
            },
            statusColumn,
            usageColumn,
            actionsColumn,
          ]
        : [
            nameColumn,
            {
              key: 'menu',
              header: t('reference.inMenu'),
              secondary: true,
              render: (row) =>
                'show_in_menu' in row && row.show_in_menu ? t('common.yes') : t('common.no'),
            },
            statusColumn,
            usageColumn,
            actionsColumn,
          ];

  return (
    <>
      <PageHeader
        title={t('nav.reference')}
        description={t('reference.hint')}
        actions={<Button onClick={() => setCreating(true)}>{t(`reference.new_${kind}`)}</Button>}
      />

      <StatusTabs
        options={[
          { value: 'categories', label: t('reference.categories') },
          { value: 'brands', label: t('reference.brands_tab') },
          { value: 'manufacturers', label: t('reference.manufacturers') },
        ]}
        value={kind}
        onChange={(next) => {
          setKind(next as ReferenceKind);
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
        emptyTitle={t('reference.empty')}
        emptyBody={t(`reference.emptyBody_${kind}`)}
      />

      <Drawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        title={editing ? editing.name_ar : t(`reference.new_${kind}`)}
      >
        {creating || editing ? (
          <ReferenceForm
            key={editing?.id ?? `new-${kind}`}
            kind={kind}
            {...(editing ? { row: editing } : {})}
            categories={allCategories.data ?? []}
            manufacturers={allManufacturers.data ?? []}
            onDone={() => {
              setCreating(false);
              setEditing(null);
            }}
          />
        ) : null}
      </Drawer>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title={t('reference.confirmDeleteTitle')}
        footer={
          <>
            <Button variant="danger" loading={remove.isPending} onClick={confirmDelete}>
              {t('common.delete')}
            </Button>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </Button>
          </>
        }
      >
        <p>{t('reference.confirmDeleteBody', { name: pendingDelete?.name_ar ?? '' })}</p>
        <p className="muted">{t('reference.deleteGuardNote')}</p>
      </Modal>
    </>
  );
}
