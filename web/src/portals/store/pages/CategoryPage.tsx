import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ProductListing } from '@/features/catalog/components/ProductListing';
import { useCategory, useProducts } from '@/features/catalog/hooks';
import { useProductPaging } from '@/features/catalog/useProductPaging';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { ListLayout } from '@/shared/layouts/ListLayout';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';

import './CategoryPage.css';

/**
 * A category page.
 *
 * ⚠️  **Subcategories appear as links rather than being hidden.**
 *
 *     The server lists the category's products and everything beneath it
 *     (`path__startswith`), so the "Medicines" page shows hundreds. Without the
 *     branch links the customer keeps scrolling through a generic list and never
 *     learns that "Painkillers" exists at all.
 *
 * ⚠️  And **the description is shown when present**: medicine categories carry
 *     warnings and dispensing guidance, and hiding them makes the field
 *     worthless in the panel.
 */
export function CategoryPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { slug } = useParams<{ slug: string }>();

  const category = useCategory(slug);
  const paging = useProductPaging();
  const query = useProducts({
    ...(slug ? { category: slug } : {}),
    ...(paging.page > 1 ? { page: paging.page } : {}),
  });

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

      <ListLayout>
        <ProductListing
          query={query}
          page={paging.page}
          onPageChange={paging.onPageChange}
          onOutOfRange={paging.onOutOfRange}
        />
      </ListLayout>
    </div>
  );
}
