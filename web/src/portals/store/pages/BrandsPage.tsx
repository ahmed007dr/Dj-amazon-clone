import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useBrands, useManufacturers } from '@/features/catalog/hooks';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';

import './BrandsPage.css';

/**
 * The brands page.
 *
 * ⚠️  **The featured ones first, under a heading that separates them.**
 *
 *     `is_featured` is a commercial decision the admin takes and one that costs
 *     an agreement with the supplier; showing the brands in a single order
 *     cancels the whole decision and makes the field decoration in the database.
 *
 * ⚠️  And **a missing logo is replaced by the first letter, not by an empty square**.
 *
 *     Most local brands have no uploaded logo; a grid full of grey squares reads
 *     as "the images did not load" rather than "no logo".
 */
export function BrandsPage() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const brands = useBrands();
  const manufacturers = useManufacturers();

  if (brands.isPending) {
    return (
      <div className="container brands-page">
        <Skeleton height="3rem" />
        <Skeleton height="14rem" />
      </div>
    );
  }

  const all = brands.data ?? [];
  const featured = all.filter((row) => row.is_featured);
  const rest = all.filter((row) => !row.is_featured);

  if (all.length === 0) {
    return (
      <div className="container">
        <PageHeader title={t('catalog.brands')} />
        <StateMessage icon="🏷️" title={t('catalog.noBrands')} body={t('catalog.noBrandsBody')} />
      </div>
    );
  }

  const card = (brand: (typeof all)[number]) => (
    <li key={brand.id}>
      <Link to={`/brands/${brand.slug}`} className="brand-card">
        {brand.logo ? (
          <img src={brand.logo} alt="" loading="lazy" />
        ) : (
          <span className="brand-card__initial" aria-hidden>
            {localized(brand, 'name').slice(0, 1)}
          </span>
        )}
        <strong>{localized(brand, 'name')}</strong>
        {brand.manufacturer ? (
          <small>{localized(brand.manufacturer, 'name')}</small>
        ) : null}
      </Link>
    </li>
  );

  return (
    <div className="container brands-page">
      <PageHeader title={t('catalog.brands')} description={t('catalog.brandsHint')} />

      {featured.length > 0 ? (
        <section>
          <h2 className="brands-page__heading">{t('catalog.featuredBrands')}</h2>
          <ul className="brands-grid">{featured.map(card)}</ul>
        </section>
      ) : null}

      {rest.length > 0 ? (
        <section>
          {featured.length > 0 ? (
            <h2 className="brands-page__heading">{t('catalog.allBrands')}</h2>
          ) : null}
          <ul className="brands-grid">{rest.map(card)}</ul>
        </section>
      ) : null}

      {/* ⚠️  Manufacturers are a text list rather than a grid: the customer
          searches by the brand ("Panadol") not by the manufacturer ("GSK"),
          and the manufacturer is reassuring context rather than a browsing
          entry point. */}
      {manufacturers.data && manufacturers.data.length > 0 ? (
        <section>
          <h2 className="brands-page__heading">{t('catalog.manufacturers')}</h2>
          <ul className="manufacturer-list">
            {manufacturers.data.map((row) => (
              <li key={row.id}>
                <strong>{localized(row, 'name')}</strong>
                {row.country ? <span>{row.country}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
