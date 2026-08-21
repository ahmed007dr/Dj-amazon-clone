import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { useCreditCheckout, useMyAccount } from '@/features/b2b/api';
import { CartIssues } from '@/features/cart/components/CartIssues';
import { CartSummary } from '@/features/cart/components/CartSummary';
import { useCart } from '@/features/cart/hooks';
import { AddressPicker } from '@/features/orders/components/AddressPicker';
import { PaymentPicker } from '@/features/orders/components/PaymentPicker';
import { ShippingPicker } from '@/features/orders/components/ShippingPicker';
import { useCheckout } from '@/features/orders/hooks';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { formatMoney } from '@/shared/utils/format';

import './CheckoutPage.css';

/**
 * ⚠️  An internal value never sent to the server.
 *
 *     The credit path does not accept `payment_method` at all — this is a marker
 *     for the frontend alone, distinguishing "on account" from the payment gateways.
 */
const CREDIT_METHOD = '__credit__';

/**
 * Checkout.
 *
 * ⚠️  The totals are returned from the server together with **the governorate
 *     and the shipping method**.
 *
 *     Choosing the address changes the shipping charge, so the governorate is
 *     passed to the cart call for the server to return correct totals. Computing
 *     shipping locally and adding it to the total produces a figure that
 *     contradicts the invoice.
 */
export function CheckoutPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const [addressId, setAddressId] = useState<string | null>(null);
  const [governorate, setGovernorate] = useState('');
  const [shippingMethod, setShippingMethod] = useState<string | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const cartQuery = useCart({
    ...(governorate ? { governorate } : {}),
    ...(shippingMethod ? { shipping_method: shippingMethod } : {}),
  });
  const checkout = useCheckout();

  // ⚠️  The credit account is read without failing the page for non-business customers.
  //
  //     `useMyAccount` returns 403 for a retail customer — a normal state, not an
  //     error. Showing "could not load" on a healthy checkout page stops a sale.
  const tradeAccount = useMyAccount();
  const creditCheckout = useCreditCheckout();

  const credit = tradeAccount.data;
  const cart = cartQuery.data;

  // ⚠️  Changing the governorate invalidates the selected shipping method.
  //
  //     "Express" is available in Cairo and unavailable in Matrouh; keeping the
  //     selection sends a code the server refuses after the customer filled everything in.
  useEffect(() => {
    setShippingMethod(null);
  }, [governorate]);

  if (cartQuery.isPending) return <Spinner />;

  if (!cart || cart.lines.length === 0) {
    return (
      <div className="container">
        <StateMessage
          icon="⛿"
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

  // ⚠️  Credit is available only with an active account and a limit sufficient for the amount.
  //
  //     Offering it for a suspended account or one over its limit means a choice
  //     refused after the whole form is filled in — and the check here runs on the
  //     same figures the server checks, and the server remains the arbiter.
  const creditAvailable =
    credit !== undefined &&
    credit.credit_status === 'ACTIVE' &&
    Number(credit.available) >= Number(cart.totals.total);

  const payingOnCredit = paymentMethod === CREDIT_METHOD;

  const ready = Boolean(addressId && shippingMethod && paymentMethod && cart.is_checkoutable);

  function handleSubmit() {
    if (!addressId || !paymentMethod) return;
    setError(null);

    const onError = (cause: unknown) => {
      // ⚠️  409 = the truth changed between showing the cart and the press (stock
      //     ran out · the product was discontinued). The server's message is
      //     specific, and refetching the cart reveals the affected line.
      setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
      void cartQuery.refetch();
    };

    if (payingOnCredit) {
      creditCheckout.mutate(
        {
          address_id: addressId,
          shipping_method_code: shippingMethod ?? '',
          customer_note: note,
        },
        {
          onSuccess: (response) => {
            void navigate(`/orders/${response.order.id}`, { replace: true });
          },
          onError,
        },
      );
      return;
    }

    checkout.mutate(
      {
        address_id: addressId,
        shipping_method_code: shippingMethod ?? '',
        payment_method: paymentMethod,
        customer_note: note,
      },
      {
        onSuccess: (response) => {
          void navigate(`/orders/${response.order.id}`, { replace: true });
        },
        onError,
      },
    );
  }

  return (
    <div className="container">
      <PageHeader title={t('checkout.title')} />

      <CartIssues issues={cart.issues} />
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <div className="checkout">
        <div className="checkout__steps">
          <section className="checkout__step surface">
            <h2 className="checkout__heading">{t('checkout.address')}</h2>
            <AddressPicker
              value={addressId}
              onChange={(id, gov) => {
                setAddressId(id);
                setGovernorate(gov);
              }}
            />
          </section>

          <section className="checkout__step surface">
            <h2 className="checkout__heading">{t('checkout.shipping')}</h2>
            <ShippingPicker
              governorate={governorate}
              subtotal={cart.totals.subtotal}
              value={shippingMethod}
              onChange={setShippingMethod}
            />
          </section>

          <section className="checkout__step surface">
            <h2 className="checkout__heading">{t('checkout.payment')}</h2>
            <PaymentPicker
              amount={cart.totals.total}
              value={paymentMethod}
              onChange={setPaymentMethod}
            />

            {/* ⚠️  Credit sits outside `PaymentPicker` deliberately.
                That list comes from the enabled payment gateways, and credit is
                not a gateway: no money moves now, and the entry lands on the
                customer's account through an entirely different server path. */}
            {creditAvailable ? (
              <label className={`checkout__credit ${payingOnCredit ? 'is-selected' : ''}`}>
                <input
                  type="radio"
                  name="payment"
                  checked={payingOnCredit}
                  onChange={() => setPaymentMethod(CREDIT_METHOD)}
                />
                <span>
                  <strong>{t('checkout.payOnCredit')}</strong>
                  <em>
                    {t('checkout.creditAvailable', {
                      amount: formatMoney(credit.available, i18n.language),
                      days: credit.payment_terms_days,
                    })}
                  </em>
                </span>
              </label>
            ) : credit && credit.credit_status === 'ACTIVE' ? (
              // The account is a business one but the limit is insufficient — said rather than hidden
              <p className="checkout__credit-note muted">
                {t('checkout.creditInsufficient', {
                  amount: formatMoney(credit.available, i18n.language),
                })}
              </p>
            ) : null}
          </section>

          <section className="checkout__step surface">
            <h2 className="checkout__heading">{t('checkout.note')}</h2>
            <textarea
              className="checkout__note"
              rows={3}
              maxLength={1000}
              value={note}
              placeholder={t('checkout.notePlaceholder')}
              aria-label={t('checkout.note')}
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
          </section>
        </div>

        <CartSummary totals={cart.totals} shippingKnown={Boolean(shippingMethod)}>
          <Button
            block
            size="lg"
            disabled={!ready}
            loading={checkout.isPending || creditCheckout.isPending}
            onClick={handleSubmit}
          >
            {t('checkout.placeOrder')}
          </Button>

          {!ready ? <p className="checkout__hint muted">{t('checkout.completeSteps')}</p> : null}
        </CartSummary>
      </div>
    </div>
  );
}
