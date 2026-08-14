import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

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

import './CheckoutPage.css';

/**
 * إتمام الشراء.
 *
 * ⚠️  الإجماليات تُعاد من الخادم مع **المحافظة وطريقة الشحن**.
 *
 *     اختيار العنوان يغيّر رسوم الشحن، فتُمرَّر المحافظة إلى نداء
 *     السلة ليعيد الخادم إجمالياتٍ صحيحة. حساب الشحن محليًا وجمعه
 *     على الإجمالي ينتج رقمًا يخالف الفاتورة.
 */
export function CheckoutPage() {
  const { t } = useTranslation();
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

  const cart = cartQuery.data;

  // ⚠️  تغيير المحافظة يُبطل طريقة الشحن المختارة.
  //
  //     «سريع» متاح في القاهرة وغير متاح في مطروح؛ إبقاء الاختيار
  //     يرسل رمزًا يرفضه الخادم بعد أن ملأ العميل كل شيء.
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

  const ready = Boolean(addressId && shippingMethod && paymentMethod && cart.is_checkoutable);

  function handleSubmit() {
    if (!addressId || !paymentMethod) return;
    setError(null);

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
        onError: (cause) => {
          // ⚠️  ٤٠٩ = تغيّرت الحقيقة بين عرض السلة والضغط (نفد
          //     المخزون · أُوقف المنتج). الرسالة من الخادم محدّدة،
          //     وإعادة جلب السلة تُظهر السطر المتأثر.
          setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
          void cartQuery.refetch();
        },
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
            loading={checkout.isPending}
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
