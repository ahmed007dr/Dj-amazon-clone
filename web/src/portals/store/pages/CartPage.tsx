import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { CartIssues } from '@/features/cart/components/CartIssues';
import { CartLineRow } from '@/features/cart/components/CartLineRow';
import { CartSummary } from '@/features/cart/components/CartSummary';
import { useAuth } from '@/features/auth/useAuth';
import { CouponBox } from '@/features/cart/components/CouponBox';
import { useCart } from '@/features/cart/hooks';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { CartIcon } from '@/shared/ui/CartIcon';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './CartPage.css';

export function CartPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isRestoring } = useAuth();
  const { data: cart, isPending, error, refetch } = useCart();

  // ⚠️  A visitor, not merely "not yet known": during the session restore `user` is
  //     still null for someone who is in fact signed in.
  const isGuest = !isRestoring && !user;

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
          icon={<CartIcon />}
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

          {/* ⚠️  Coupons belong to accounts. A guest is told so, with the way in,
              rather than shown a box the server would only refuse. */}
          <div className="cart-page__coupon">
            {isGuest ? (
              <p className="cart-page__guest-note muted">
                {t('guest.couponsNeedAccount')}{' '}
                <Link to="/login" state={{ from: location.pathname }}>
                  {t('auth.signIn')}
                </Link>
              </p>
            ) : (
              <CouponBox snapshot={cart} />
            )}
          </div>
        </section>

        {/* ⚠️  Shipping is not known here: the governorate is chosen at checkout.
            Showing zero suggests it is free and then an amount appears — the
            most common reason for cart abandonment. */}
        <CartSummary totals={cart.totals} shippingKnown={false} freeShipping={cart.free_shipping}>
          <Button
            block
            size="lg"
            disabled={!cart.is_checkoutable}
            onClick={() => void navigate('/checkout')}
          >
            {isGuest ? t('guest.continueAsGuest') : t('cart.checkout')}
          </Button>

          {/* Guest checkout is the primary path (no friction); signing in is
              offered beside it, with the way back to the cart's next step. */}
          {isGuest ? (
            <Button
              block
              variant="secondary"
              disabled={!cart.is_checkoutable}
              onClick={() => void navigate('/login', { state: { from: '/checkout' } })}
            >
              {t('guest.signInToCheckout')}
            </Button>
          ) : null}

          {!cart.is_checkoutable ? (
            <p className="cart-page__blocked muted">{t('cart.blockedHint')}</p>
          ) : null}
        </CartSummary>
      </div>
    </div>
  );
}
