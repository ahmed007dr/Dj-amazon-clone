import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import {
  listAdminProducts,
  useDeleteProduct,
  useProductFormOptions,
  useRestoreProduct,
  type AdminProduct,
} from '@/features/catalog/adminApi';
import { ProductForm } from '@/portals/admin/components/ProductForm';
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
import { formatMoney } from '@/shared/utils/format';

import './AdminProductsPage.css';

/** اللوح المفتوح — نموذج أو صور. */
type Panel =
  | { mode: 'create' }
  | { mode: 'edit'; product: AdminProduct }
  | { mode: 'images'; product: AdminProduct };

export function AdminProductsPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [search, setSearch] = useState('');
  const [active, setActive] = useState('');
  const [showDeleted, setShowDeleted] = useState('');
  const [page, setPage] = useState(1);

  // ⚠️  لوح لا مسار.
  //
  //     صفحة بمسار خاص تعني مغادرة القائمة وفقدان البحث والصفحة
  //     والفلاتر — والأدمن يحرّر عشرة منتجات متتالية فيعود إلى
  //     الصفحة الأولى في كل مرة.
  const [panel, setPanel] = useState<Panel | null>(null);

  // ⚠️  الحذف يمرّ بتأكيد يذكر **اسم المنتج**.
  //
  //     «هل أنت متأكد؟» المجرّدة تُضغط بلا قراءة؛ والاسم في الرسالة
  //     هو ما يجعل الأدمن يلاحظ أنه ضغط على الصف الخطأ.
  const [pendingDelete, setPendingDelete] = useState<AdminProduct | null>(null);

  const debouncedSearch = useDebounced(search);

  const query = useQuery({
    queryKey: ['admin', 'products', debouncedSearch, active, showDeleted, page],
    queryFn: () =>
      listAdminProducts({
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(active ? { is_active: active } : {}),
        ...(showDeleted ? { include_deleted: showDeleted } : {}),
        page,
      }),
    staleTime: 60 * 1000,
  });

  // ⚠️  يُجلب هنا أيضًا لحلّ **أسماء الفئات** في الجدول.
  //
  //     الخادم يرسل `category` معرّفًا لا كائنًا، فكان العمود يعرض
  //     فراغًا في كل صف بلا خطأ. والاستعلام نفسه يخدم النموذج
  //     فلا نداء إضافي.
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
        // ⚠️  الرابط إلى صفحة المتجر العامة: الأدمن يريد رؤية ما
        //     يراه العميل بالضبط قبل أن يحكم على المنتج.
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
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (product) =>
        // ⚠️  المحذوف يعرض **الاسترجاع وحده**.
        //
        //     تعديل منتج محذوف أو رفع صوره عمل يضيع: لا يراه أحد
        //     ما دام محذوفًا. الخطوة الأولى إرجاعه.
        product.deleted_at ? (
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
            <Button size="sm" variant="ghost" onClick={() => setPendingDelete(product)}>
              {t('common.delete')}
            </Button>
          </span>
        ),
    },
  ];

  const hasFilters = Boolean(search || active || showDeleted);

  const panelTitle =
    panel?.mode === 'create'
      ? t('products.create')
      : panel
        ? localized(panel.product, 'name')
        : '';

  return (
    <>
      <PageHeader
        title={t('nav.products')}
        {...(query.data ? { description: t('admin.total', { count: query.data.count }) } : {})}
        actions={
          <Button onClick={() => setPanel({ mode: 'create' })}>{t('products.create')}</Button>
        }
      />

      <FilterBar
        hasFilters={hasFilters}
        onClear={() => {
          setSearch('');
          setActive('');
          setShowDeleted('');
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
        {/* ⚠️  اللوح يُركَّب عند الفتح فقط، ومفتاحه يتغيّر مع المنتج.
            إبقاؤه مركّبًا يجعل النموذج يحتفظ بمسوّدة منتج سابق،
            ويعرض صور المنتج السابق للحظة عند فتح التالي. */}
        {panel?.mode === 'images' ? (
          <ProductImagesPanel key={panel.product.id} productId={panel.product.id} />
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
