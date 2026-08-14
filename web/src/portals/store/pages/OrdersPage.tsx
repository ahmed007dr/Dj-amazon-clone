import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import {
  OrderStatusBadge,
  PaymentStatusBadge,
} from '@/features/orders/components/OrderStatusBadge';
import { useMyOrders } from '@/features/orders/hooks';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate, formatMoney } from '@/shared/utils/format';

import './OrdersPage.css';

export function OrdersPage() {
  const { t, i18n } = useTranslation();
  const { data, isPending, error, refetch } = useMyOrders();

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

  const orders = data.results;

  return (
    <div className="container">
      <PageHeader title={t('nav.orders')} />

      {orders.length === 0 ? (
        <StateMessage icon="▤" title={t('orders.emptyTitle')} body={t('orders.emptyBody')} />
      ) : (
        <ul className="orders-list">
          {orders.map((order) => (
            <li key={order.id}>
              {/* ⚠️  الرابط بالمعرّف UUID والرقم للعرض فقط (ADR-25) */}
              <Link to={`/orders/${order.id}`} className="order-row surface">
                <span className="order-row__number">{order.number}</span>

                <span className="order-row__badges">
                  <OrderStatusBadge status={order.status} />
                  <PaymentStatusBadge status={order.payment_status} />
                </span>

                <span className="order-row__meta muted">
                  {formatDate(order.created_at, i18n.language)} ·{' '}
                  {t('cart.itemCount', { count: order.item_count })}
                </span>

                <span className="order-row__total">
                  {formatMoney(order.grand_total, i18n.language)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
