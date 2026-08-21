import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ProductGrid } from '@/features/catalog/components/ProductGrid';
import { useProducts } from '@/features/catalog/hooks';
import { useBrand } from '@/shared/branding/useBrand';
import { Button } from '@/shared/ui/Button';

import './HomePage.css';

export function HomePage() {
  const { t } = useTranslation();
  const { name, tagline } = useBrand();

  // ⚠️  Featured only — we do not fetch every product for a page that shows eight.
  const query = useProducts({ ordering: '-created_at', limit: 8 });
  const products = query.data?.pages[0]?.results ?? [];

  return (
    <div className="container stack">
      <section className="hero surface">
        <h1 className="hero__title">{name}</h1>
        {tagline ? <p className="hero__tagline muted">{tagline}</p> : null}
        <Button>
          <Link to="/products" className="hero__cta">
            {t('nav.catalog')}
          </Link>
        </Button>
      </section>

      <section>
        <div className="row-between">
          <h2 className="home-section__title">{t('catalog.title')}</h2>
          <Link to="/products">{t('common.more')}</Link>
        </div>

        <ProductGrid
          products={products}
          isLoading={query.isPending}
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </section>
    </div>
  );
}
