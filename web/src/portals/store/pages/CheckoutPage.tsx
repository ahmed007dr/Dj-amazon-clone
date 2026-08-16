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
 * ⚠️  قيمة داخلية لا تُرسَل إلى الخادم.
 *
 *     مسار الآجل لا يقبل `payment_method` إطلاقًا — هذه علامة
 *     للواجهة وحدها تميّز «على الحساب» عن بوابات الدفع.
 */
const CREDIT_METHOD = '__credit__';

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

  // ⚠️  الحساب الآجل يُقرأ بلا إفشال الصفحة لغير التجاري.
  //
  //     `useMyAccount` يردّ ٤٠٣ لعميل التجزئة — وهي حالة عادية لا
  //     خطأ. عرض «تعذّر التحميل» على صفحة إتمام سليمة يوقف بيعة.
  const tradeAccount = useMyAccount();
  const creditCheckout = useCreditCheckout();

  const credit = tradeAccount.data;
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

  // ⚠️  الآجل متاح فقط بحساب نشط وحدٍّ يكفي المبلغ.
  //
  //     عرضه لحساب معلَّق أو تجاوز حدَّه يعني اختيارًا يُرفض بعد
  //     ملء النموذج كاملًا — والفحص هنا يقع على نفس الأرقام التي
  //     يفحصها الخادم، وهو يبقى الحَكَم.
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
      // ⚠️  ٤٠٩ = تغيّرت الحقيقة بين عرض السلة والضغط (نفد
      //     المخزون · أُوقف المنتج). الرسالة من الخادم محدّدة،
      //     وإعادة جلب السلة تُظهر السطر المتأثر.
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

            {/* ⚠️  الآجل خارج `PaymentPicker` عمدًا.
                تلك القائمة تأتي من بوابات الدفع المفعّلة، والآجل
                ليس بوابة: لا مال ينتقل الآن، والقيد يقع على حساب
                العميل بمسار خادم مختلف تمامًا. */}
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
              // الحساب تجاري لكن الحد لا يكفي — يُقال بدل الإخفاء
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
