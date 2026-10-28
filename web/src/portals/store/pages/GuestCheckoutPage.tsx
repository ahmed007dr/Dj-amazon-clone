import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { CartIssues } from '@/features/cart/components/CartIssues';
import { CartSummary } from '@/features/cart/components/CartSummary';
import { useCart } from '@/features/cart/hooks';
import { GuestCheckoutForm } from '@/features/orders/components/GuestCheckoutForm';
import {
  EMPTY_GUEST_FORM,
  looksLikeEgyptianMobile,
  type GuestFormValues,
} from '@/features/orders/guestForm';
import { ShippingPicker } from '@/features/orders/components/ShippingPicker';
import { useGuestCheckout, usePaymentMethods } from '@/features/orders/hooks';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { CartIcon } from '@/shared/ui/CartIcon';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './CheckoutPage.css';
import './GuestCheckoutPage.css';

/** A fresh retry key for one checkout attempt. */
function newAttemptKey(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  }
}

/**
 * Checkout for a visitor with no account.
 *
 * ⚠️  **Cash on delivery only, and the owner rings to confirm.**
 *
 *     So there is no payment step to choose from — one fixed card says what
 *     will happen — no coupon box (coupons belong to accounts), and no saved
 *     addresses. What replaces them is the plain form: who, where, how to reach
 *     them.
 *
 * ⚠️  One `Idempotency-Key` per attempt.
 *
 *     A double click, or a retry after a dropped connection, must not become two
 *     orders. The key is made once when the page opens and reused until the
 *     order exists — the server returns the same order for the same key.
 */
export function GuestCheckoutPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const [form, setForm] = useState<GuestFormValues>(EMPTY_GUEST_FORM);
  const [shippingMethod, setShippingMethod] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof GuestFormValues, string>>>(
    {},
  );

  const attemptKey = useRef(newAttemptKey());

  const cartQuery = useCart({
    ...(form.governorate ? { governorate: form.governorate } : {}),
    ...(shippingMethod ? { shipping_method: shippingMethod } : {}),
  });
  const checkout = useGuestCheckout();
  const cart = cartQuery.data;

  // Cash on delivery must actually be enabled — the list is the gateways on right now
  const methods = usePaymentMethods(cart?.totals.total ?? '0');
  const codAvailable = methods.data?.some((option) => option.method === 'COD') ?? false;

  // ⚠️  Changing the governorate invalidates the chosen shipping method — "Express"
  //     may exist in Cairo and not in Matrouh.
  useEffect(() => {
    setShippingMethod(null);
  }, [form.governorate]);

  if (cartQuery.isPending) return <Spinner />;

  if (!cart || cart.lines.length === 0) {
    return (
      <div className="container">
        <StateMessage
          icon={<CartIcon />}
          title={t('cart.emptyTitle')}
          action={
            <Button variant="secondary">
              <Link to="/products" className="checkout__link">
                {t('nav.catalog')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  const required: (keyof GuestFormValues)[] = [
    'recipient_name',
    'phone',
    'email',
    'governorate',
    'city',
    'street',
  ];
  const filled = required.every((key) => form[key].trim().length > 0);
  const ready =
    filled &&
    looksLikeEgyptianMobile(form.phone) &&
    Boolean(shippingMethod) &&
    codAvailable &&
    cart.is_checkoutable;

  function handleSubmit() {
    if (!shippingMethod) return;
    setError(null);
    setAccessDenied(false);
    setFieldErrors({});

    checkout.mutate(
      {
        recipient_name: form.recipient_name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        governorate: form.governorate,
        city: form.city.trim(),
        street: form.street.trim(),
        shipping_method_code: shippingMethod,
        customer_note: form.customer_note.trim(),
        language: document.documentElement.lang.startsWith('en') ? 'en' : 'ar',
        idempotency_key: attemptKey.current,
        website: form.website,
      },
      {
        onSuccess: (response) => {
          // The email is passed along (in memory, not in the URL) so the next page
          // can offer "create an account" with the address already filled in.
          void navigate(`/order/guest/${encodeURIComponent(response.tracking_token)}`, {
            replace: true,
            state: { placed: true, email: form.email.trim() },
          });
        },
        onError: (cause) => {
          if (!isApiError(cause)) {
            setError(t('state.errorTitle'));
            return;
          }

          // ⚠️  The product needs an account: say so and offer the way in, rather
          //     than a bare "not available" the visitor cannot act on.
          if (cause.status === 409 && cause.code === 'PRODUCT_ACCESS_DENIED') {
            setAccessDenied(true);
          }

          const next: Partial<Record<keyof GuestFormValues, string>> = {};
          for (const key of required) {
            const message = cause.fieldError(key);
            if (message) next[key] = message;
          }
          setFieldErrors(next);

          setError(
            cause.isRateLimited
              ? t('guest.tooManyAttempts')
              : Object.keys(next).length > 0
                ? t('guest.fixFields')
                : cause.displayMessage,
          );
          // The truth may have changed (stock ran out) — refetch shows which line
          void cartQuery.refetch();
        },
      },
    );
  }

  return (
    <div className="container">
      <PageHeader
        title={t('checkout.title')}
        description={t('guest.checkoutSubtitle')}
        actions={
          <Button variant="ghost" size="sm">
            <Link
              to="/login"
              state={{ from: location.pathname }}
              className="checkout__link"
            >
              {t('guest.haveAccount')}
            </Link>
          </Button>
        }
      />

      <CartIssues issues={cart.issues} />

      {error ? (
        <Alert tone="danger">
          <p>{error}</p>
          {accessDenied ? (
            <p>
              <Link to="/login" state={{ from: location.pathname }} className="guest-checkout__cta">
                {t('guest.signInForRestricted')}
              </Link>
            </p>
          ) : null}
        </Alert>
      ) : null}

      <div className="checkout">
        <div className="checkout__steps">
          <section className="checkout__step surface">
            <h2 className="checkout__heading">{t('guest.yourDetails')}</h2>
            <GuestCheckoutForm
              value={form}
              onChange={setForm}
              errors={fieldErrors}
              disabled={checkout.isPending}
            />
          </section>

          <section className="checkout__step surface">
            <h2 className="checkout__heading">{t('checkout.shipping')}</h2>
            <ShippingPicker
              governorate={form.governorate}
              subtotal={cart.totals.subtotal}
              eligibleAmount={cart.totals.net_sales}
              value={shippingMethod}
              onChange={setShippingMethod}
            />
          </section>

          <section className="checkout__step surface">
            <h2 className="checkout__heading">{t('checkout.payment')}</h2>
            {methods.isPending ? (
              <Spinner />
            ) : codAvailable ? (
              <div className="guest-checkout__cod">
                <strong>{t('guest.codTitle')}</strong>
                <p className="muted">{t('guest.codBody')}</p>
              </div>
            ) : (
              <StateMessage
                icon="⌀"
                title={t('checkout.noPayment')}
                body={t('checkout.noPaymentHint')}
              />
            )}
          </section>
        </div>

        <CartSummary
          totals={cart.totals}
          shippingKnown={Boolean(shippingMethod)}
          freeShipping={cart.free_shipping}
        >
          <Button
            block
            size="lg"
            disabled={!ready}
            loading={checkout.isPending}
            onClick={handleSubmit}
          >
            {t('checkout.placeOrder')}
          </Button>

          {!ready ? <p className="checkout__hint muted">{t('checkout.completeSteps')}</p> : null}

          <p className="checkout__hint muted">
            <Link to="/order/find" className="checkout__link">
              {t('guest.findMyOrder')}
            </Link>
          </p>
        </CartSummary>
      </div>
    </div>
  );
}
