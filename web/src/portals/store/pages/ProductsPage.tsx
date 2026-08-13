import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CategoryFilter } from '@/features/catalog/components/CategoryFilter';
import { ProductGrid } from '@/features/catalog/components/ProductGrid';
import { SearchBox } from '@/features/catalog/components/SearchBox';
import { useProducts } from '@/features/catalog/hooks';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useIsDesktop } from '@/shared/hooks/useMediaQuery';
import { ListLayout } from '@/shared/layouts/ListLayout';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';

export function ProductsPage() {
  const { t } = useTranslation();
  const isDesktop = useIsDesktop();

  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // ⚠️  بلا تأخير يصير كل حرف نداءً، وتصل الاستجابات بترتيب غير مضمون
  const debouncedSearch = useDebounced(search);

  const query = useProducts({
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(category ? { category } : {}),
  });

  const products = query.data?.pages.flatMap((page) => page.results) ?? [];

  const filters = (
    <CategoryFilter
      value={category}
      onChange={(next) => {
        setCategory(next);
        setFiltersOpen(false);
      }}
    />
  );

  return (
    <div className="container">
      <ListLayout
        header={<PageHeader title={t('catalog.title')} />}
        toolbar={
          <>
            <SearchBox value={search} onChange={setSearch} />
            {!isDesktop && (
              <Button
                variant="secondary"
                onClick={() => {
                  setFiltersOpen(true);
                }}
              >
                {t('common.filters')}
              </Button>
            )}
          </>
        }
        // ⚠️  الفلاتر شريط جانبي على الديسكتوب و Drawer على الهاتف —
        //     نفس المكوّن في الحالتين، فلا تتفرّع النسختان
        {...(isDesktop ? { filters } : {})}
        footer={
          query.hasNextPage ? (
            <Button
              variant="secondary"
              loading={query.isFetchingNextPage}
              onClick={() => {
                void query.fetchNextPage();
              }}
            >
              {t('common.more')}
            </Button>
          ) : null
        }
      >
        <ProductGrid
          products={products}
          isLoading={query.isPending}
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </ListLayout>

      {!isDesktop && (
        <Drawer
          open={filtersOpen}
          onClose={() => {
            setFiltersOpen(false);
          }}
          title={t('common.filters')}
        >
          {filters}
        </Drawer>
      )}
    </div>
  );
}
