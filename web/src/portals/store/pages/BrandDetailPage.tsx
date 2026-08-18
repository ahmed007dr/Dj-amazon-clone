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
 * صفحة ماركة.
 *
 * ⚠️  **رأس الماركة ثم منتجاتها — لا قائمة منتجات بعنوان.**
 *
 *     الوصف والمصنّع وبلده هي ما يطمئن مشتري الدواء قبل أن يقرأ
 *     سعرًا. حذفها يجعل الصفحة نسخة من صفحة المنتجات بفلتر، ولا
 *     سبب لوجودها أصلًا.
 *
 * ⚠️  و**الفلترة بالـ slug على الخادم** لا بترشيح المصفوفة هنا.
 *
 *     الترشيح في الواجهة يعمل على الصفحة المحمَّلة وحدها، فتبدو
 *     ماركة بمنتج واحد بينما لها عشرون في الصفحات التالية.
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
