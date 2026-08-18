import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ProductGrid } from '@/features/catalog/components/ProductGrid';
import { useCategory, useProducts } from '@/features/catalog/hooks';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { ListLayout } from '@/shared/layouts/ListLayout';
import { Button } from '@/shared/ui/Button';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';

import './CategoryPage.css';

/**
 * صفحة فئة.
 *
 * ⚠️  **الفئات الفرعية تظهر روابط لا تختفي.**
 *
 *     الخادم يُدرج منتجات الفئة وكل ما تحتها (`path__startswith`)،
 *     فصفحة «أدوية» تعرض المئات. بلا روابط الفروع يبقى العميل
 *     يمرّر في قائمة عامة ولا يعرف أن «مسكنات» موجودة أصلًا.
 *
 * ⚠️  و**الوصف يُعرض إن وُجد**: فئات الأدوية تحمل تحذيرات
 *     وإرشادات صرف، وإخفاؤها يجعل الحقل بلا قيمة في اللوحة.
 */
export function CategoryPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { slug } = useParams<{ slug: string }>();

  const category = useCategory(slug);
  const query = useProducts(slug ? { category: slug } : {});

  const products = query.data?.pages.flatMap((page) => page.results) ?? [];

  if (category.isPending) {
    return (
      <div className="container category-page">
        <Skeleton height="6rem" />
        <Skeleton height="14rem" />
      </div>
    );
  }

  if (isApiError(category.error) && category.error.status === 404) {
    return (
      <div className="container">
        <StateMessage icon="📂" title={t('catalog.categoryNotFound')} />
      </div>
    );
  }

  if (!category.data) {
    return (
      <div className="container">
        <StateMessage icon="⚠" title={t('state.errorTitle')} />
      </div>
    );
  }

  const children = category.data.children ?? [];

  return (
    <div className="container category-page">
      <header className="category-page__head">
        <h1>{localized(category.data, 'name')}</h1>
        {localized(category.data, 'description') ? (
          <p>{localized(category.data, 'description')}</p>
        ) : null}
      </header>

      {children.length > 0 ? (
        <nav className="category-children" aria-label={t('catalog.subcategories')}>
          {children.map((child) => (
            <Link key={child.id} to={`/categories/${child.slug}`}>
              {localized(child, 'name')}
            </Link>
          ))}
        </nav>
      ) : null}

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
