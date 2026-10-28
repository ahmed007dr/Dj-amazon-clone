import { useRef, useState } from 'react';
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
import { PriceTag } from '@/shared/ui/PriceTag';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';
import { StatusTabs, type TabOption } from '@/shared/ui/StatusTabs';
import { TabPanel } from '@/shared/ui/TabPanel';
import { tabDomId } from '@/shared/ui/tabIds';
import { formatMoney } from '@/shared/utils/format';

import './ProductDetailPage.css';

type DetailTab = 'description' | 'specs' | 'reviews';

/** The base of the tab/panel DOM ids — one definition, shared by the tab list and the panels. */
const TABS_ID = 'pdp';

/**
 * The page's own loading state.
 *
 * ⚠️  A skeleton in the **same grid** as the real page, not a spinner in a blank page: the
 *     gallery square and the buy box are reserved from the first frame, so the page does not
 *     jump when the product arrives and the footer is not pulled up behind a spinner.
 */
function ProductDetailSkeleton() {
  const { t } = useTranslation();

  return (
    <div className="container pdp" aria-busy="true">
      <span className="visually-hidden" role="status">
        {t('common.loading')}
      </span>

      <div className="pdp__crumbs" aria-hidden>
        <Skeleton width="14rem" height="1rem" />
      </div>

      <div className="pdp__grid" aria-hidden>
        <div className="pdp__media">
          <div className="pdp__skeleton-media">
            <Skeleton height="auto" radius="var(--radius-lg)" />
          </div>
        </div>

        <div className="pdp__info">
          <Skeleton width="30%" height="1.5rem" radius="var(--radius-pill)" />
          <Skeleton width="85%" height="2rem" />
          <Skeleton width="35%" height="1.25rem" />
          <Skeleton height="6.5rem" radius="var(--radius)" />
          <Skeleton width="100%" height="3.25rem" radius="var(--radius)" />
        </div>
      </div>
    </div>
  );
}

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
  // `null` until the shopper picks one — the first tab that exists is then the default
  const [tab, setTab] = useState<DetailTab | null>(null);
  const detailsRef = useRef<HTMLDivElement>(null);

  const availability = useAvailability(product ? [product.id] : []);

  if (isPending) return <ProductDetailSkeleton />;

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

  // ⚠️  The price, the old price and the saving all come from the server, for exactly what the
  //     shopper has chosen: a size inside a colour → that variant; a colour → the colour; no colour
  //     yet → the cheapest swatch ("from"); a plain size → that variant; otherwise the product.
  //     The page never works out a discount itself — `compare_at_price` arrives only when it is
  //     above what *this* shopper pays (a student price can make it vanish, or grow).
  //
  //     `price` is the legacy sum above when the server did not send one (an older payload).
  const priceSource: {
    price?: string | undefined;
    compare_at_price?: string | null | undefined;
    discount_percent?: number | null | undefined;
  } =
    hasColors && selectedColor
      ? (selected ?? selectedColor)
      : hasColors && lowest !== null
        ? (colors.find((color) => Number.parseFloat(color.price) === lowest) ?? product)
        : (selected ?? product);
  const shownPrice = priceSource.price ?? displayPrice;

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
  const outOfStock = stock?.is_available === false;
  const cannotAdd =
    needsColor ||
    needsVariant ||
    (hasColors && selectedColor !== null && cartVariantId === null) ||
    outOfStock;

  // What the disabled button is waiting for. At most one of the two applies: a variant is only
  // asked for once a colour is settled.
  const hint = needsColor
    ? t('catalog.colors.pickColor')
    : needsVariant
      ? t('catalog.pickVariant')
      : null;

  const description = localized(product, 'description');
  const shortDescription = localized(product, 'short_description');

  // ── The tabs under the buy box ─────────────────────────────────────
  // Description only when there is one — an empty tab is a dead end.
  const tabs: (TabOption & { value: DetailTab })[] = [
    ...(description ? [{ value: 'description' as const, label: t('catalog.description') }] : []),
    { value: 'specs', label: t('catalog.specs') },
    {
      value: 'reviews',
      label: t('catalog.reviews'),
      ...(product.rating.count > 0 ? { count: product.rating.count } : {}),
    },
  ];
  const activeTab = tabs.find((option) => option.value === tab)?.value ?? tabs[0]!.value;

  // ⚠️  The rating under the title is a way *in* to the reviews, not a dead label: it opens the
  //     reviews tab, brings the section into view and moves focus to the tab so a keyboard user
  //     lands where the page took them (`preventScroll` — the smooth scroll below does the move).
  const showReviews = () => {
    setTab('reviews');
    document.getElementById(tabDomId(TABS_ID, 'reviews'))?.focus({ preventScroll: true });
    detailsRef.current?.scrollIntoView({ block: 'start' });
  };

  const money = (value: string) => formatMoney(value, i18n.language);
  const was = priceSource.compare_at_price;

  const addToCart = (
    <AddToCartButton
      productId={product.id}
      {...(cartVariantId ? { variantId: cartVariantId } : {})}
      block
      disabled={cannotAdd}
    />
  );

  return (
    <div className="container pdp">
      <nav className="breadcrumb pdp__crumbs" aria-label={t('common.back')}>
        <Link to="/products">{t('nav.catalog')}</Link>
        {product.category ? (
          <>
            <span aria-hidden>/</span>
            <Link to={`/products?category=${product.category.slug}`}>
              {localized(product.category, 'name')}
            </Link>
          </>
        ) : null}
        <span aria-hidden>/</span>
        <span className="pdp__crumb-current truncate" aria-current="page">
          {name}
        </span>
      </nav>

      <div className="pdp__grid">
        <div className="pdp__media">
          <ProductGallery key={galleryKey} images={galleryImages} alt={name} />
        </div>

        <div className="pdp__info">
          <header className="pdp__head">
            <div className="pdp__meta">
              {product.brand ? (
                <Link to={`/products?brand=${product.brand.slug}`} className="pdp__brand">
                  {localized(product.brand, 'name')}
                </Link>
              ) : null}
              <span className="pdp__sku">
                {t('catalog.sku')}: <bdi>{product.sku}</bdi>
              </span>
            </div>

            <h1 className="pdp__title">{name}</h1>

            {product.rating.count > 0 ? (
              <button
                type="button"
                className="pdp__rating"
                title={t('catalog.reviews')}
                onClick={showReviews}
              >
                <StarRating value={product.rating.average} count={product.rating.count} />
              </button>
            ) : null}
          </header>

          <div className="pdp__price-panel">
            <PriceTag
              variant="detail"
              price={shownPrice}
              compareAt={priceSource.compare_at_price}
              percent={priceSource.discount_percent}
              prefix={priceIsFrom ? t('catalog.colors.from') : undefined}
            />

            <div className="pdp__status">
              <StockBadge availability={stock} />
            </div>
          </div>

          {/* ⚠️  Prescriptions are outside the current scope of work, and the field
              exists to avoid a later migration. Showing it when it is true
              prevents selling an item that requires a prescription through a
              path that does not check for one. */}
          {product.requires_prescription ? (
            <Alert tone="warning">{t('catalog.prescriptionRequired')}</Alert>
          ) : null}

          {shortDescription ? <p className="pdp__summary">{shortDescription}</p> : null}

          {hasColors || variants.length > 0 ? (
            <div className="pdp__options">
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
            </div>
          ) : null}

          {/* ⚠️  Two homes for the buy button, one visible at a time (CSS, not state — no resize
              listener, no flash). From a tablet up it sits in the card; on a phone it moves to the
              bar pinned to the bottom edge, so it is never a scroll away from the options it
              depends on. The bar carries the price too, since the card's has scrolled off. */}
          <div className="pdp__action">
            {hint ? <p className="pdp__hint">{hint}</p> : null}
            {addToCart}
          </div>
        </div>
      </div>

      <div ref={detailsRef} className="pdp__details">
        <StatusTabs
          id={TABS_ID}
          label={t('catalog.details')}
          options={tabs}
          value={activeTab}
          onChange={(next) => {
            setTab(next as DetailTab);
          }}
        />

        {description ? (
          <TabPanel
            id={TABS_ID}
            value="description"
            active={activeTab === 'description'}
            className="pdp__panel"
          >
            <p className="pdp__body">{description}</p>
          </TabPanel>
        ) : null}

        <TabPanel id={TABS_ID} value="specs" active={activeTab === 'specs'} className="pdp__panel">
          <ProductSpecs product={product} />
        </TabPanel>

        {/* ⚠️  `keepMounted`: the panel holds a half-written review. Unmounting it on a tab
            change would throw that text away, and a shopper comparing the specs mid-sentence
            would come back to an empty form. */}
        <TabPanel
          id={TABS_ID}
          value="reviews"
          active={activeTab === 'reviews'}
          keepMounted
          className="pdp__panel"
        >
          {/* ⚠️  The id is required for writing: the server links the review to the
              product by its id rather than by `slug` — and the latter is
              theoretically changeable. */}
          {slug ? <ReviewList slug={slug} productId={product.id} /> : null}
        </TabPanel>
      </div>

      {/* The phone's buy bar — see the note on `pdp__action` */}
      <div className="pdp__bar">
        <div className="pdp__bar-info">
          <span className="pdp__bar-price" aria-hidden>
            {priceIsFrom ? (
              <span className="pdp__bar-from">{t('catalog.colors.from')} </span>
            ) : null}
            {money(shownPrice)}
          </span>

          {hint ? (
            <span className="pdp__bar-note">{hint}</span>
          ) : outOfStock ? (
            <span className="pdp__bar-note pdp__bar-note--bad">{t('catalog.outOfStock')}</span>
          ) : was ? (
            <s className="pdp__bar-was" aria-hidden>
              {money(was)}
            </s>
          ) : null}
        </div>

        <div className="pdp__bar-action">{addToCart}</div>
      </div>
    </div>
  );
}
