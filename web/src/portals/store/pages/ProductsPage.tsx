import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { CategoryFilter } from '@/features/catalog/components/CategoryFilter';
import { ProductListing } from '@/features/catalog/components/ProductListing';
import { SearchBox } from '@/features/catalog/components/SearchBox';
import { useProducts } from '@/features/catalog/hooks';
import { useProductPaging } from '@/features/catalog/useProductPaging';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useIsDesktop } from '@/shared/hooks/useMediaQuery';
import { ListLayout } from '@/shared/layouts/ListLayout';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';

/**
 * ⚠️  **The search, the category and the page all live in the address.**
 *
 *     With only the page in the URL, Back from a product opens `?page=3` of the *unfiltered*
 *     catalogue — page 3 of a list the shopper was not looking at. The three travel together
 *     or the page number means nothing.
 *
 *     Filters `replace` the entry (Back from a filter should leave the list, as on the bundles
 *     page) and clear `page`: page 4 of "all" has no relation to page 4 of "gloves". A page
 *     change pushes — see `useProductPaging`.
 */
export function ProductsPage() {
  const { t } = useTranslation();
  const isDesktop = useIsDesktop();

  const [params, setParams] = useSearchParams();
  const paging = useProductPaging();
  const urlSearch = params.get('search') ?? '';
  const category = params.get('category') ?? undefined;

  // ⚠️  The box keeps its own text. A controlled input fed from the router lags a transition
  //     behind the keystroke, and the lag eats characters (worst with an Arabic keyboard).
  const [search, setSearch] = useState(urlSearch);

  // ⚠️  With no delay every character becomes a call, and the responses arrive in an unguaranteed order
  const debouncedSearch = useDebounced(search);

  // The address follows the settled text, one way: it is the box that is the source while typing
  useEffect(() => {
    if (debouncedSearch === urlSearch) return;
    setParams(
      (previous) => {
        const out = new URLSearchParams(previous);
        if (debouncedSearch) out.set('search', debouncedSearch);
        else out.delete('search');
        out.delete('page');
        return out;
      },
      { replace: true },
    );
  }, [debouncedSearch, urlSearch, setParams]);

  // ⚠️  Until the address has caught up with a new search term, the page in it still belongs to
  //     the OLD term — asking for it under the new one fetches page 4 of a list with two pages.
  const page = debouncedSearch === urlSearch ? paging.page : 1;

  const query = useProducts({
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(category ? { category } : {}),
    ...(page > 1 ? { page } : {}),
  });

  const [filtersOpen, setFiltersOpen] = useState(false);

  const filters = (
    <CategoryFilter
      value={category}
      onChange={(next) => {
        setParams(
          (previous) => {
            const out = new URLSearchParams(previous);
            if (next) out.set('category', next);
            else out.delete('category');
            out.delete('page');
            return out;
          },
          { replace: true },
        );
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
        // ⚠️  The filters are a sidebar on desktop and a drawer on a phone —
        //     the same component in both cases, so the two versions do not diverge
        {...(isDesktop ? { filters } : {})}
      >
        <ProductListing
          query={query}
          page={page}
          onPageChange={paging.onPageChange}
          onOutOfRange={paging.onOutOfRange}
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
