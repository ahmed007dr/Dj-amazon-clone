import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ProductGrid } from '@/features/catalog/components/ProductGrid';
import { useBrand, useProducts } from '@/features/catalog/hooks';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { ListLayout } from '@/shared/layouts/ListLayout';
import { Button } from '@/shared/ui/Button';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';

import './BrandDetailPage.css';

/**
 * A brand page.
 *
 * ⚠️  **The brand header, then its products — not a product list with a title.**
 *
 *     The description, the manufacturer and its country are what reassure a
 *     medicine buyer before they read a price. Removing them makes the page a
 *     copy of the products page with a filter, and there is no reason for it to
 *     exist at all.
 *
 * ⚠️  And **filtering is by slug on the server**, not by filtering the array here.
 *
 *     Filtering in the frontend operates on the loaded page alone, so a brand
 *     looks as though it has one product while it has twenty on the following pages.
 */
export function BrandDetailPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { slug } = useParams<{ slug: string }>();

  const brand = useBrand(slug);
  const query = useProducts(slug ? { brand: slug } : {});

  const products = query.data?.pages.flatMap((page) => page.results) ?? [];

  if (brand.isPending) {
    return (
      <div className="container brand-detail">
        <Skeleton height="8rem" />
        <Skeleton height="14rem" />
      </div>
    );
  }

  if (isApiError(brand.error) && brand.error.status === 404) {
    return (
      <div className="container">
        <StateMessage icon="🏷️" title={t('catalog.brandNotFound')} />
      </div>
    );
  }

  if (!brand.data) {
    return (
      <div className="container">
        <StateMessage icon="⚠" title={t('state.errorTitle')} />
      </div>
    );
  }

  return (
    <div className="container brand-detail">
      <header className="brand-detail__head">
        {brand.data.logo ? (
          <img src={brand.data.logo} alt="" />
        ) : (
          <span className="brand-detail__initial" aria-hidden>
            {localized(brand.data, 'name').slice(0, 1)}
          </span>
        )}

        <div>
          <h1>{localized(brand.data, 'name')}</h1>
          {brand.data.manufacturer ? (
            <p className="brand-detail__maker">
              {localized(brand.data.manufacturer, 'name')}
              {brand.data.manufacturer.country ? ` · ${brand.data.manufacturer.country}` : ''}
            </p>
          ) : null}
          {localized(brand.data, 'description') ? (
            <p className="brand-detail__about">{localized(brand.data, 'description')}</p>
          ) : null}
        </div>
      </header>

      <ListLayout
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
    </div>
  );
}
