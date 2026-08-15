import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { CancelOrderButton } from '@/features/orders/components/CancelOrderButton';
import {
  OrderStatusBadge,
  PaymentStatusBadge,
} from '@/features/orders/components/OrderStatusBadge';
import { useOrder } from '@/features/orders/hooks';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDateTime, formatMoney } from '@/shared/utils/format';

import './OrderDetailPage.css';

export function OrderDetailPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { id } = useParams<{ id: string }>();
  const { data: order, isPending, error } = useOrder(id);

  if (isPending) return <Spinner />;

  // ⚠️  `404` قد يعني «غير موجود» أو «ليس لك» — والخادم لا يفرّق
  //     عمدًا لمنع تعداد الطلبات. الواجهة لا تخمّن أيهما.
  if (error || !order) {
    return (
      <div className="container">
        <StateMessage icon="⌀" title={t('state.notFoundTitle')} body={t('state.notFoundBody')} />
      </div>
    );
  }

  const money = (value: string) => formatMoney(value, i18n.language);

  return (
    <div className="container">
      <PageHeader
        title={order.number}
        description={formatDateTime(order.created_at, i18n.language)}
        actions={
          <>
            <OrderStatusBadge status={order.status} />
            <PaymentStatusBadge status={order.payment_status} />
          </>
        }
      />

      <div className="order-detail">
        <section className="order-detail__lines surface">
          {/* ⚠️  الأسماء من لقطة السطر لا من المنتج الحالي (ADR-30):
              الفاتورة القديمة يجب ألا تتغيّر بتغيّر اسم المنتج اليوم */}
          {order.lines.map((line) => (
            <article key={line.id} className="order-line">
              <div className="order-line__info">
                <strong>{localized(line, 'product_name')}</strong>
                <span className="muted">{line.product_sku}</span>
              </div>

              <span className="order-line__qty muted">
                {line.quantity} × {money(line.unit_price)}
              </span>

              <span className="order-line__total">{money(line.total)}</span>
            </article>
          ))}
        </section>

        <aside className="order-detail__side">
          <section className="surface order-detail__box">
            <h2 className="order-detail__heading">{t('cart.summary')}</h2>
            <dl className="order-detail__rows">
              <div>
                <dt>{t('cart.subtotal')}</dt>
                <dd>{money(order.subtotal)}</dd>
              </div>
              {Number.parseFloat(order.discount_total) > 0 ? (
                <div>
                  <dt>{t('cart.discount')}</dt>
                  <dd>−{money(order.discount_total)}</dd>
                </div>
              ) : null}
              <div>
                <dt>{t('cart.tax')}</dt>
                <dd>{money(order.tax_total)}</dd>
              </div>
              <div>
                <dt>{t('cart.shipping')}</dt>
                <dd>{money(order.shipping_total)}</dd>
              </div>
              <div className="order-detail__total">
                <dt>{t('cart.total')}</dt>
                <dd>{money(order.grand_total)}</dd>
              </div>
            </dl>
          </section>

          <section className="surface order-detail__box">
            <h2 className="order-detail__heading">{t('checkout.address')}</h2>
            <address className="order-detail__address">
              <strong>{order.recipient_name}</strong>
              <span className="muted">{order.recipient_phone}</span>
              <span className="muted">
                {order.governorate} — {order.city}
              </span>
              <span className="muted">{order.street}</span>
            </address>
          </section>

          {/* ⚠️  `can_cancel` من الخادم — يُحسب من آلة الحالة نفسها
              لا من قائمة حالات موازية هنا */}
          {order.can_cancel ? (
            <section className="surface order-detail__box">
              <h2 className="order-detail__heading">{t('orders.cancel')}</h2>
              <CancelOrderButton orderId={order.id} />
            </section>
          ) : null}

          {order.cancellation_reason ? (
            <section className="surface order-detail__box">
              <h2 className="order-detail__heading">{t('orders.cancelled')}</h2>
              <p className="muted">{order.cancellation_reason}</p>
            </section>
          ) : null}

          {order.status_history.length > 0 ? (
            <section className="surface order-detail__box">
              <h2 className="order-detail__heading">{t('orders.timeline')}</h2>
              <ol className="order-detail__timeline">
                {order.status_history.map((event) => (
                  <li key={`${event.to_status}-${event.created_at}`}>
                    <span>{t(`orderStatus.${event.to_status}`)}</span>
                    <span className="muted">
                      {formatDateTime(event.created_at, i18n.language)}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
