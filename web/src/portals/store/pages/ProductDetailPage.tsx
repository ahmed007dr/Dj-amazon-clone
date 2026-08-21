import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { AddToCartButton } from '@/features/cart/components/AddToCartButton';
import { ProductGallery } from '@/features/catalog/components/ProductGallery';
import { ProductSpecs } from '@/features/catalog/components/ProductSpecs';
import { ReviewList } from '@/features/catalog/components/ReviewList';
import { StarRating } from '@/features/catalog/components/StarRating';
import { StockBadge } from '@/features/catalog/components/StockBadge';
import { VariantPicker } from '@/features/catalog/components/VariantPicker';
import { useAvailability, useProduct } from '@/features/catalog/hooks';
import { isApiError } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatMoney } from '@/shared/utils/format';

import './ProductDetailPage.css';

export function ProductDetailPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { slug } = useParams<{ slug: string }>();

  const { data: product, isPending, error } = useProduct(slug);
  const [variantId, setVariantId] = useState<string | null>(null);

  const availability = useAvailability(product ? [product.id] : []);

  if (isPending) return <Spinner />;

  if (error || !product) {
    /**
     * ⚠️  `404` may mean "does not exist" or "not yours".
     *
     *     The server does not distinguish them deliberately, to prevent
     *     enumeration of restricted products — and a product hidden by an
     *     access policy gives exactly the same response. The frontend does not
     *     guess which, but it suggests signing in because that is the only
     *     path that might open it.
     */
    const restricted = isApiError(error) && error.isNotFound;

    return (
      <div className="container">
        <StateMessage
          icon="⌀"
          title={t('state.notFoundTitle')}
          body={restricted ? t('catalog.maybeRestricted') : t('state.notFoundBody')}
          action={
            <Button variant="secondary">
              <Link to="/products" className="product-page__link">
                {t('nav.catalog')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  const name = localized(product, 'name');
  const stock = availability.data?.[product.id];
  const variants = product.variants;

  // ⚠️  The variant's price difference is added to the reference price — and the server
  //     is what settles the final price when it is added to the cart. This is for display only.
  const selected = variants.find((variant) => variant.id === variantId);
  const displayPrice = selected
    ? (Number.parseFloat(product.base_price) + Number.parseFloat(selected.price_adjustment)).toFixed(
        2,
      )
    : product.base_price;

  const needsVariant = variants.length > 0 && !variantId;

  return (
    <div className="container">
      <nav className="breadcrumb" aria-label={t('common.back')}>
        <Link to="/products">{t('nav.catalog')}</Link>
        {product.category ? (
          <>
            <span aria-hidden>/</span>
            <Link to={`/products?category=${product.category.slug}`}>
              {localized(product.category, 'name')}
            </Link>
          </>
        ) : null}
      </nav>

      <div className="product-page">
        <div className="product-page__media">
          <ProductGallery images={product.images} alt={name} />
        </div>

        <div className="product-page__info">
          <h1 className="product-page__title">{name}</h1>

          {product.brand ? (
            <Link
              to={`/products?brand=${product.brand.slug}`}
              className="product-page__brand muted"
            >
              {localized(product.brand, 'name')}
            </Link>
          ) : null}

          {product.rating.count > 0 ? (
            <StarRating value={product.rating.average} count={product.rating.count} />
          ) : null}

          <p className="product-page__price">{formatMoney(displayPrice, i18n.language)}</p>

          <StockBadge availability={stock} />

          {/* ⚠️  Prescriptions are outside the current scope of work, and the field
              exists to avoid a later migration. Showing it when it is true
              prevents selling an item that requires a prescription through a
              path that does not check for one. */}
          {product.requires_prescription ? (
            <Alert tone="warning">{t('catalog.prescriptionRequired')}</Alert>
          ) : null}

          {localized(product, 'short_description') ? (
            <p className="product-page__summary">{localized(product, 'short_description')}</p>
          ) : null}

          <VariantPicker variants={variants} value={variantId} onChange={setVariantId} />

          <div className="product-page__action">
            {needsVariant ? (
              <p className="product-page__hint muted">{t('catalog.pickVariant')}</p>
            ) : null}

            <AddToCartButton
              productId={product.id}
              {...(variantId ? { variantId } : {})}
              block
              disabled={needsVariant || stock?.is_available === false}
            />
          </div>
        </div>
      </div>

      {localized(product, 'description') ? (
        <section className="product-page__section">
          <h2 className="product-page__heading">{t('catalog.description')}</h2>
          <p className="product-page__body">{localized(product, 'description')}</p>
        </section>
      ) : null}

      <section className="product-page__section">
        <h2 className="product-page__heading">{t('catalog.specs')}</h2>
        <ProductSpecs product={product} />
      </section>

      <section className="product-page__section">
        <h2 className="product-page__heading">
          {t('catalog.reviews')}
          {product.rating.count > 0 ? ` (${product.rating.count})` : ''}
        </h2>
        {/* ⚠️  The id is required for writing: the server links the review to the
            product by its id rather than by `slug` — and the latter is
            theoretically changeable. */}
        {slug ? <ReviewList slug={slug} productId={product.id} /> : null}
      </section>
    </div>
  );
}
