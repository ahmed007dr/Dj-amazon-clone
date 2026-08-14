import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { listAdminProducts, type AdminProduct } from '@/features/catalog/adminApi';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { formatMoney } from '@/shared/utils/format';

export function AdminProductsPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const [search, setSearch] = useState('');
  const [active, setActive] = useState('');
  const [page, setPage] = useState(1);

  const debouncedSearch = useDebounced(search);

  const query = useQuery({
    queryKey: ['admin', 'products', debouncedSearch, active, page],
    queryFn: () =>
      listAdminProducts({
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(active ? { is_active: active } : {}),
        page,
      }),
    staleTime: 60 * 1000,
  });

  const columns: Column<AdminProduct>[] = [
    {
      key: 'sku',
      header: t('catalog.sku'),
      render: (product) => (
        <code style={{ direction: 'ltr' }}>{product.sku}</code>
      ),
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
      render: (product) => (product.category ? localized(product.category, 'name') : '—'),
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
  ];

  const hasFilters = Boolean(search || active);

  return (
    <>
      <PageHeader
        title={t('nav.products')}
        {...(query.data ? { description: t('admin.total', { count: query.data.count }) } : {})}
      />

      <FilterBar
        hasFilters={hasFilters}
        onClear={() => {
          setSearch('');
          setActive('');
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
    </>
  );
}
