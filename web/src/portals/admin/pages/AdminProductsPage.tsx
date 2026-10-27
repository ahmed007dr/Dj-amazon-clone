import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import {
  listAdminProducts,
  useDeleteProduct,
  useProductFormOptions,
  useRestoreProduct,
  type AdminProduct,
  type AuditUser,
} from '@/features/catalog/adminApi';
import { ExportButton } from '@/portals/admin/components/ExportButton';
import { ProductForm } from '@/portals/admin/components/ProductForm';
import { ProductHistoryPanel } from '@/portals/admin/components/ProductHistoryPanel';
import { ProductImagesPanel } from '@/portals/admin/components/ProductImagesPanel';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Modal } from '@/shared/ui/Modal';
import { Pagination } from '@/shared/ui/Pagination';
import { useToast } from '@/shared/ui/useToast';
import { formatDateTime, formatMoney } from '@/shared/utils/format';

import './AdminProductsPage.css';

/** The open panel — the form or the images. */
type Panel =
  | { mode: 'create' }
  | { mode: 'edit'; product: AdminProduct }
  | { mode: 'images'; product: AdminProduct }
  | { mode: 'history'; product: AdminProduct };

export function AdminProductsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const localized = useLocalized();
  const { notify } = useToast();

  const [search, setSearch] = useState('');
  const [active, setActive] = useState('');
  const [showDeleted, setShowDeleted] = useState('');
  // '' = newest added first (the server default); '-updated_at' = recently modified first.
  const [ordering, setOrdering] = useState('');
  const [page, setPage] = useState(1);

  // ⚠️  A panel, not a route.
  //
  //     A page with its own route means leaving the list and losing the search,
  //     the page and the filters — and the admin edits ten products in a row and
  //     returns to the first page every time.
  const [panel, setPanel] = useState<Panel | null>(null);

  // ⚠️  Deletion goes through a confirmation that names **the product**.
  //
  //     A bare "are you sure?" is pressed without reading; and the name in the
  //     message is what makes the admin notice they pressed the wrong row.
  const [pendingDelete, setPendingDelete] = useState<AdminProduct | null>(null);

  const debouncedSearch = useDebounced(search);

  const query = useQuery({
    queryKey: ['admin', 'products', debouncedSearch, active, showDeleted, ordering, page],
    queryFn: () =>
      listAdminProducts({
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(active ? { is_active: active } : {}),
        ...(showDeleted ? { include_deleted: showDeleted } : {}),
        ...(ordering ? { ordering } : {}),
        page,
      }),
    staleTime: 60 * 1000,
  });

  // ⚠️  Fetched here as well to resolve **the category names** in the table.
  //
  //     The server sends `category` as an id rather than an object, so the column
  //     displayed a blank in every row with no error. And the same query serves
  //     the form, so there is no extra call.
  const options = useProductFormOptions();

  const categoryNames = new Map(
    (options.data?.categories ?? []).map((row) => [row.id, localized(row, 'name')]),
  );

  const remove = useDeleteProduct();
  const restore = useRestoreProduct();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const confirmDelete = () => {
    if (!pendingDelete) return;
    remove.mutate(pendingDelete.id, {
      onSuccess: () => {
        notify(t('products.deleted'), 'success');
        setPendingDelete(null);
      },
      onError: fail,
    });
  };

  const auditCell = (who: AuditUser | null | undefined, when: string) => (
    <div className="admin-products__audit">
      <strong title={who?.email}>{who?.name ?? '—'}</strong>
      <span className="muted">{formatDateTime(when, i18n.language)}</span>
    </div>
  );

  const columns: Column<AdminProduct>[] = [
    {
      key: 'sku',
      header: t('catalog.sku'),
      render: (product) => <code style={{ direction: 'ltr' }}>{product.sku}</code>,
    },
    {
      key: 'name',
      header: t('admin.productName'),
      render: (product) => (
        // ⚠️  The link goes to the public store page: the admin wants to see exactly
        //     what the customer sees before judging the product.
        <Link to={`/products/${product.slug}`} target="_blank">
          {localized(product, 'name')}
        </Link>
      ),
    },
    {
      key: 'category',
      header: t('catalog.category'),
      secondary: true,
      render: (product) =>
        (product.category ? categoryNames.get(product.category) : null) ?? '—',
    },
    {
      key: 'price',
      header: t('admin.basePrice'),
      align: 'end',
      render: (product) => formatMoney(product.base_price, i18n.language),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (product) =>
        product.deleted_at ? (
          <Badge tone="neutral">{t('admin.deleted')}</Badge>
        ) : product.is_active ? (
          <Badge tone="success">{t('admin.active')}</Badge>
        ) : (
          <Badge tone="warning">{t('admin.inactive')}</Badge>
        ),
    },
    {
      // ⚠️  Who and when, in one cell each — a name without a date (or the reverse)
      //     answers half of "who touched this and when?". `—` for products that
      //     predate the audit columns: showing nobody is honest, guessing is not.
      key: 'created',
      header: t('products.addedBy'),
      secondary: true,
      render: (product) => auditCell(product.created_by, product.created_at),
    },
    {
      key: 'modified',
      header: t('products.modifiedBy'),
      secondary: true,
      render: (product) => auditCell(product.updated_by, product.updated_at),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (product) =>
        // ⚠️  A deleted one shows **restore alone** (and its history, which is where
        //     "who deleted it" is answered).
        //
        //     Editing a deleted product or uploading its images is wasted work: nobody
        //     sees it while it is deleted. The first step is to bring it back.
        product.deleted_at ? (
          <span className="admin-products__actions">
            <Button
              size="sm"
              variant="ghost"
              loading={restore.isPending}
              onClick={() =>
                restore.mutate(product.id, {
                  onSuccess: () => notify(t('products.restored'), 'success'),
                  onError: fail,
                })
              }
            >
              {t('products.restore')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setPanel({ mode: 'history', product })}
            >
              {t('products.history.open')}
            </Button>
          </span>
        ) : (
          <span className="admin-products__actions">
            <Button size="sm" variant="ghost" onClick={() => setPanel({ mode: 'edit', product })}>
              {t('common.edit')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setPanel({ mode: 'images', product })}
            >
              {t('images.manage')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setPanel({ mode: 'history', product })}
            >
              {t('products.history.open')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPendingDelete(product)}>
              {t('common.delete')}
            </Button>
          </span>
        ),
    },
  ];

  const hasFilters = Boolean(search || active || showDeleted || ordering);

  const panelTitle =
    panel?.mode === 'create'
      ? t('products.create')
      : panel?.mode === 'history'
        ? `${t('products.history.title')} · ${localized(panel.product, 'name')}`
        : panel
          ? localized(panel.product, 'name')
          : '';

  return (
    <>
      <PageHeader
        title={t('nav.products')}
        {...(query.data ? { description: t('admin.total', { count: query.data.count }) } : {})}
        actions={
          <>
            {/* ⚠️  Secondary, and beside "add" rather than buried in a menu.
                Adding ten thousand items one form at a time is not a thing
                anyone does twice — the admin who needs this needs to find it
                on the screen where they gave up. */}
            {/* ⚠️  It carries the filters currently on screen — searching for a
                brand and then exporting should give that brand, not the whole
                catalogue. The `catalogue` dataset is the readable one; the
                round-trip file lives on the export screen where its purpose
                can be explained. */}
            <ExportButton
              dataset="catalogue"
              size="md"
              params={{
                ...(active === 'false' ? { include_inactive: 'true' } : {}),
              }}
            />
            <Button variant="secondary" onClick={() => void navigate('/admin/products/import')}>
              {t('imports.action')}
            </Button>
            <Button onClick={() => setPanel({ mode: 'create' })}>{t('products.create')}</Button>
          </>
        }
      />

      <FilterBar
        hasFilters={hasFilters}
        onClear={() => {
          setSearch('');
          setActive('');
          setShowDeleted('');
          setOrdering('');
          setPage(1);
        }}
      >
        <FilterSearch
          value={search}
          onChange={(next) => {
            setSearch(next);
            setPage(1);
          }}
          placeholder={t('admin.searchProducts')}
        />

        <FilterSelect
          value={active}
          label={t('admin.status')}
          options={[
            { value: 'true', label: t('admin.active') },
            { value: 'false', label: t('admin.inactive') },
          ]}
          onChange={(next) => {
            setActive(next);
            setPage(1);
          }}
        />

        <FilterSelect
          value={showDeleted}
          label={t('products.deletedFilter')}
          options={[{ value: 'true', label: t('products.includeDeleted') }]}
          onChange={(next) => {
            setShowDeleted(next);
            setPage(1);
          }}
        />

        {/* ⚠️  "Recently modified" answers "what did the team touch today?" without
            opening each product; the default stays newest-added-first. */}
        <FilterSelect
          value={ordering}
          label={t('products.sortBy')}
          options={[
            { value: '-updated_at', label: t('products.sortRecentlyModified') },
            { value: 'updated_at', label: t('products.sortLeastRecentlyModified') },
            { value: 'created_at', label: t('products.sortOldestAdded') },
          ]}
          onChange={(next) => {
            setOrdering(next);
            setPage(1);
          }}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        rowKey={(product) => product.id}
        isLoading={query.isPending}
        error={query.error}
        emptyTitle={t('state.emptyTitle')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Drawer open={panel !== null} onClose={() => setPanel(null)} title={panelTitle}>
        {/* ⚠️  The panel is mounted only on opening, and its key changes with the product.
            Leaving it mounted makes the form keep a previous product's draft,
            and shows the previous product's images for a moment when the next one opens. */}
        {panel?.mode === 'images' ? (
          <ProductImagesPanel key={panel.product.id} productId={panel.product.id} />
        ) : null}

        {panel?.mode === 'history' ? (
          <ProductHistoryPanel key={panel.product.id} productId={panel.product.id} />
        ) : null}

        {panel?.mode === 'create' ? (
          <ProductForm key="create" onDone={() => setPanel(null)} />
        ) : null}

        {panel?.mode === 'edit' ? (
          <ProductForm
            key={panel.product.id}
            product={panel.product}
            onDone={() => setPanel(null)}
          />
        ) : null}
      </Drawer>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title={t('products.confirmDeleteTitle')}
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
        <p>
          {t('products.confirmDeleteBody', {
            name: pendingDelete ? localized(pendingDelete, 'name') : '',
          })}
        </p>
        <p className="admin-products__soft-note">{t('products.softDeleteNote')}</p>
      </Modal>
    </>
  );
}
