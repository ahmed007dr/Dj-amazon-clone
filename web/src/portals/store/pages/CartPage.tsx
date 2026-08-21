import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { CartIssues } from '@/features/cart/components/CartIssues';
import { CartLineRow } from '@/features/cart/components/CartLineRow';
import { CartSummary } from '@/features/cart/components/CartSummary';
import { CouponBox } from '@/features/cart/components/CouponBox';
import { useCart } from '@/features/cart/hooks';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './CartPage.css';

export function CartPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: cart, isPending, error, refetch } = useCart();

  if (isPending) return <Spinner />;

  if (error) {
    return (
      <div className="container">
        <StateMessage
          icon="⚠"
          title={t('state.errorTitle')}
          action={
            <Button variant="secondary" onClick={() => void refetch()}>
              {t('common.retry')}
            </Button>
          }
        />
      </div>
    );
  }

  if (cart.lines.length === 0) {
    return (
      <div className="container">
        <StateMessage
          icon="⛿"
          title={t('cart.emptyTitle')}
          body={t('cart.emptyBody')}
          action={
            <Button variant="secondary">
              <Link to="/products" className="cart-page__link">
                {t('nav.catalog')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="container">
      <PageHeader title={t('nav.cart')} />

      {/* ⚠️  Problems first — whoever cannot buy needs the reason in the
          first thing they see, not at the bottom of a long list */}
      <CartIssues issues={cart.issues} />

      <div className="cart-page">
        <section className="cart-page__lines">
          {cart.lines.map((line) => (
            <CartLineRow key={line.id ?? line.product_id} line={line} />
          ))}

          <div className="cart-page__coupon">
            <CouponBox snapshot={cart} />
          </div>
        </section>

        {/* ⚠️  Shipping is not known here: the governorate is chosen at checkout.
            Showing zero suggests it is free and then an amount appears — the
            most common reason for cart abandonment. */}
        <CartSummary totals={cart.totals} shippingKnown={false}>
          <Button
            block
            size="lg"
            disabled={!cart.is_checkoutable}
            onClick={() => void navigate('/checkout')}
          >
            {t('cart.checkout')}
          </Button>

          {!cart.is_checkoutable ? (
            <p className="cart-page__blocked muted">{t('cart.blockedHint')}</p>
          ) : null}
        </CartSummary>
      </div>
    </div>
  );
}
