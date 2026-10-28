import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { VariantTag } from '@/features/catalog/components/VariantTag';
import { useAdminOrder } from '@/features/orders/adminHooks';
import {
  OrderStatusBadge,
  PaymentStatusBadge,
} from '@/features/orders/components/OrderStatusBadge';
import { OrderTransitions } from '@/features/orders/components/OrderTransitions';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDateTime, formatMoney } from '@/shared/utils/format';

import './AdminOrderDetailPage.css';

export function AdminOrderDetailPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { id } = useParams<{ id: string }>();
  const { data: order, isPending, error } = useAdminOrder(id);

  if (isPending) return <Spinner />;
  if (error || !order) return <StateMessage icon="⌀" title={t('state.notFoundTitle')} />;

  const money = (value: string) => formatMoney(value, i18n.language);

  return (
    <>
      <nav className="breadcrumb">
        <Link to="/admin/orders">{t('nav.orders')}</Link>
      </nav>

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

      <section className="surface admin-order__box">
        <h2 className="admin-order__heading">{t('admin.actions')}</h2>
        <OrderTransitions orderId={order.id} status={order.status} />
      </section>

      <div className="admin-order">
        <section className="surface admin-order__box">
          <h2 className="admin-order__heading">{t('admin.items')}</h2>
          {order.lines.map((line) => (
            <div key={line.id} className="admin-order__line">
              <span>
                {localized(line, 'product_name')}{' '}
                <VariantTag
                  hex={line.color_hex}
                  color={localized(line, 'color_name')}
                  variant={localized(line, 'variant_name')}
                />
              </span>
              <span className="muted">{line.variant_sku || line.product_sku}</span>
              <span className="muted">
                {line.quantity} × {money(line.unit_price)}
              </span>
              <strong>{money(line.total)}</strong>
            </div>
          ))}
        </section>

        <aside className="admin-order__side">
          <section className="surface admin-order__box">
            <h2 className="admin-order__heading">{t('admin.customer')}</h2>

            {/* ⚠️  A guest order has no account to look up — the contact block is
                the whole customer, and the phone is the point: the owner rings it
                to confirm before the order moves on. */}
            {order.is_guest ? (
              <>
                <p>
                  <Badge tone="info">{t('guest.badge')}</Badge>
                </p>
                <Alert tone="warning">{t('guest.adminHint')}</Alert>
                <dl className="admin-order__facts">
                  <div>
                    <dt>{t('account.recipientName')}</dt>
                    <dd>{order.recipient_name}</dd>
                  </div>
                  <div>
                    <dt>{t('auth.phone')}</dt>
                    <dd style={{ direction: 'ltr' }}>
                      <a href={`tel:${order.recipient_phone}`}>{order.recipient_phone}</a>
                    </dd>
                  </div>
                  <div>
                    <dt>{t('auth.email')}</dt>
                    <dd style={{ direction: 'ltr' }}>{order.contact_email}</dd>
                  </div>
                  <div>
                    <dt>{t('guest.adminLanguage')}</dt>
                    <dd>{order.contact_language === 'en' ? 'English' : 'العربية'}</dd>
                  </div>
                </dl>
              </>
            ) : (
              <dl className="admin-order__facts">
                <div>
                  <dt>{t('auth.email')}</dt>
                  <dd style={{ direction: 'ltr' }}>{order.customer_email}</dd>
                </div>
                <div>
                  <dt>{t('admin.customerNumber')}</dt>
                  <dd style={{ direction: 'ltr' }}>{order.customer_number}</dd>
                </div>
                {order.claimed_at ? (
                  <div>
                    <dt>{t('guest.adminClaimed')}</dt>
                    <dd>{formatDateTime(order.claimed_at, i18n.language)}</dd>
                  </div>
                ) : null}
              </dl>
            )}
          </section>

          <section className="surface admin-order__box">
            <h2 className="admin-order__heading">{t('checkout.address')}</h2>
            <address className="admin-order__address">
              <strong>{order.recipient_name}</strong>
              <span className="muted" style={{ direction: 'ltr' }}>
                {order.recipient_phone}
              </span>
              <span className="muted">
                {order.governorate} — {order.city}
              </span>
              <span className="muted">{order.street}</span>
            </address>
          </section>

          <section className="surface admin-order__box">
            <h2 className="admin-order__heading">{t('cart.summary')}</h2>
            <dl className="admin-order__facts">
              <div>
                <dt>{t('cart.subtotal')}</dt>
                <dd>{money(order.subtotal)}</dd>
              </div>
              <div>
                <dt>{t('cart.discount')}</dt>
                <dd>−{money(order.discount_total)}</dd>
              </div>
              <div>
                <dt>{t('cart.tax')}</dt>
                <dd>{money(order.tax_total)}</dd>
              </div>
              <div>
                <dt>{t('cart.shipping')}</dt>
                <dd>{money(order.shipping_total)}</dd>
              </div>
              <div className="admin-order__total">
                <dt>{t('cart.total')}</dt>
                <dd>{money(order.grand_total)}</dd>
              </div>
            </dl>
          </section>

          {order.status_history.length > 0 ? (
            <section className="surface admin-order__box">
              <h2 className="admin-order__heading">{t('orders.timeline')}</h2>
              <ol className="admin-order__timeline">
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
    </>
  );
}
