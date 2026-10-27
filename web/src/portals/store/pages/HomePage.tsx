import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ProductGrid } from '@/features/catalog/components/ProductGrid';
import { useProducts } from '@/features/catalog/hooks';
import { useBrand } from '@/shared/branding/useBrand';
import { useHero } from '@/shared/branding/useHero';

import './HomePage.css';

export function HomePage() {
  const { t } = useTranslation();
  const { name, tagline } = useBrand();
  const hero = useHero();

  // ⚠️  A picture that fails to load (a deleted file, a CDN hiccup) must not leave a dark
  //     scrim over an empty box with white text on the page background. The failed address is
  //     remembered, and the hero drops back to the gradient it had before pictures existed —
  //     keyed by URL, so uploading another image tries again.
  const [failedImage, setFailedImage] = useState('');
  const image = hero.image && hero.image !== failedImage ? hero.image : '';

  // Every editable text falls back to what the page showed before they existed
  const headline = hero.title || name;
  const subtitle = hero.subtitle || tagline;
  const ctaLabel = hero.ctaLabel || t('nav.catalog');

  // ⚠️  Featured only — we do not fetch every product for a page that shows eight.
  const query = useProducts({ ordering: '-created_at', limit: 8 });
  const products = query.data?.pages[0]?.results ?? [];

  return (
    <div className="container stack">
      <section className={`hero ${image ? 'hero--media' : 'surface'}`}>
        {image ? (
          <>
            {/* Decorative: the headline carries the meaning, so the picture has no alt text.
                It is the largest thing above the fold, hence `high` and no lazy loading. */}
            <img
              className="hero__media"
              src={image}
              alt=""
              decoding="async"
              fetchPriority="high"
              onError={() => {
                setFailedImage(image);
              }}
            />
            <div className="hero__scrim" aria-hidden="true" />
          </>
        ) : null}

        <div className="hero__content">
          <h1 className="hero__title">{headline}</h1>
          {subtitle ? <p className="hero__tagline">{subtitle}</p> : null}

          {/* ⚠️  A link styled as a button, not a button wrapping a link: nested interactive
              elements make two tab stops and a click target that is only the inner text. */}
          {hero.cta.external ? (
            <a
              className="btn btn--primary btn--lg hero__cta"
              href={hero.cta.href}
              rel="noopener noreferrer"
            >
              {ctaLabel}
            </a>
          ) : (
            <Link className="btn btn--primary btn--lg hero__cta" to={hero.cta.href}>
              {ctaLabel}
            </Link>
          )}
        </div>
      </section>

      <section>
        <div className="home-section__header">
          <h2 className="home-section__title">{t('catalog.title')}</h2>
          <Link to="/products" className="home-section__link">
            {t('common.more')}
          </Link>
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
