import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { AddToCartButton } from '@/features/cart/components/AddToCartButton';
import { ColorPicker } from '@/features/catalog/components/ColorPicker';
import { ProductGallery } from '@/features/catalog/components/ProductGallery';
import { ProductSpecs } from '@/features/catalog/components/ProductSpecs';
import { ReviewList } from '@/features/catalog/components/ReviewList';
import { StarRating } from '@/features/catalog/components/StarRating';
import { StockBadge } from '@/features/catalog/components/StockBadge';
import { VariantPicker } from '@/features/catalog/components/VariantPicker';
import { useAvailability, useProduct } from '@/features/catalog/hooks';
import type { Availability } from '@/features/catalog/types';
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
  // ⚠️  Two independent choices. A colour is what the shopper picks first; a *variant*
  //     is picked only when the product has plain variants (sizes), or when the chosen
  //     colour itself comes in several (a size matrix imported with colour columns).
  const [colorId, setColorId] = useState<string | null>(null);
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
  const productStock = availability.data?.[product.id];
  const colors = product.colors;
  const hasColors = colors.length > 0;

  // ⚠️  A product with exactly one colour has nothing to choose: it is selected for the shopper.
  const selectedColor =
    colors.find((color) => color.id === colorId) ?? (colors.length === 1 ? colors[0]! : null);

  // The variants the shopper still has to choose between: with colours, those of the chosen
  // colour (normally exactly one — then there is no picker); without, all of them.
  const variants = hasColors
    ? selectedColor
      ? product.variants.filter((variant) => variant.color === selectedColor.id)
      : []
    : product.variants;

  const colorVariantId = hasColors && variants.length <= 1 ? (selectedColor?.variant_id ?? null) : null;
  const effectiveVariantId = hasColors
    ? variants.length > 1
      ? variants.some((variant) => variant.id === variantId)
        ? variantId
        : null
      : colorVariantId
    : variantId;

  const selected = product.variants.find((variant) => variant.id === effectiveVariantId);

  // ⚠️  Display only — the server settles the price when the line is added to the cart.
  //
  //     With a colour, `color.price` is already what *this customer* pays (price list →
  //     colour → product → variant difference), so nothing is added up here except the
  //     step from the colour's first variant to the size the shopper picked inside it.
  //     Before a colour is chosen, the lowest swatch price is shown ("from") when they differ.
  const colorPrices = colors.map((color) => Number.parseFloat(color.price));
  const lowest = hasColors ? Math.min(...colorPrices) : null;
  const pricesDiffer = hasColors && colorPrices.some((price) => price !== lowest);

  let displayPrice = product.base_price;
  let priceIsFrom = false;
  if (hasColors && selectedColor) {
    const first = product.variants.find((variant) => variant.id === selectedColor.variant_id);
    const step =
      selected && first
        ? Number.parseFloat(selected.price_adjustment) - Number.parseFloat(first.price_adjustment)
        : 0;
    displayPrice = (Number.parseFloat(selectedColor.price) + step).toFixed(2);
  } else if (hasColors && lowest !== null) {
    displayPrice = lowest.toFixed(2);
    priceIsFrom = pricesDiffer;
  } else if (selected) {
    displayPrice = (
      Number.parseFloat(product.base_price) + Number.parseFloat(selected.price_adjustment)
    ).toFixed(2);
  }

  // The colour's own availability when one is chosen; otherwise the product's.
  const stock: Availability | undefined = selectedColor
    ? {
        product_id: product.id,
        is_available: selectedColor.is_available,
        is_low: selectedColor.is_low,
        available: selectedColor.available,
      }
    : productStock;

  // ⚠️  The colour's own photos, else the product's main ones. And the gallery is
  //     **re-keyed** on the choice: it keeps the slide you were on in its own state,
  //     and a new colour opening on "photo 4" of a gallery with two is a blank frame.
  const colorImages = selectedColor?.images ?? [];
  const galleryImages = colorImages.length > 0 ? colorImages : product.images;
  const galleryKey = colorImages.length > 0 && selectedColor ? selectedColor.id : 'base';

  const needsColor = hasColors && !selectedColor;
  const needsVariant = hasColors
    ? !needsColor && variants.length > 1 && !effectiveVariantId
    : variants.length > 0 && !variantId;
  const cartVariantId = hasColors ? effectiveVariantId : variantId;
  const cannotAdd =
    needsColor ||
    needsVariant ||
    (hasColors && selectedColor !== null && cartVariantId === null) ||
    stock?.is_available === false;

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
          <ProductGallery key={galleryKey} images={galleryImages} alt={name} />
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

          <p className="product-page__price">
            {priceIsFrom ? (
              <span className="product-page__price-from">{t('catalog.colors.from')} </span>
            ) : null}
            {formatMoney(displayPrice, i18n.language)}
          </p>

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

          <ColorPicker
            colors={colors}
            value={selectedColor?.id ?? null}
            onChange={(next) => {
              setColorId(next);
              // A size chosen inside another colour does not carry over
              setVariantId(null);
            }}
          />

          <VariantPicker variants={variants} value={variantId} onChange={setVariantId} />

          <div className="product-page__action">
            {needsColor ? (
              <p className="product-page__hint muted">{t('catalog.colors.pickColor')}</p>
            ) : null}
            {needsVariant ? (
              <p className="product-page__hint muted">{t('catalog.pickVariant')}</p>
            ) : null}

            <AddToCartButton
              productId={product.id}
              {...(cartVariantId ? { variantId: cartVariantId } : {})}
              block
              disabled={cannotAdd}
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
