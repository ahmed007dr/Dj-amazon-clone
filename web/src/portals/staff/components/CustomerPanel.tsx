import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCustomerOrders, type AssignedCustomer } from '@/features/employees/api';
import { OrderStatusBadge } from '@/features/orders/components/OrderStatusBadge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate } from '@/shared/utils/format';

import { NewOrderForm } from './NewOrderForm';

import './CustomerPanel.css';

/**
 * لوح العميل: تاريخه ثم إنشاء طلب له.
 *
 * ⚠️  **التاريخ قبل النموذج — والترتيب هو الفائدة.**
 *
 *     المندوب يتصل بالعميل ليبيع؛ وأول ما يحتاجه هو ما اشتراه
 *     آخر مرة. فتح نموذج فارغ فوق الشاشة يجعله يسأل العميل عمّا
 *     يعرفه النظام.
 */
export function CustomerPanel({ customer }: { customer: AssignedCustomer }) {
  const { t, i18n } = useTranslation();
  const [creating, setCreating] = useState(false);

  const orders = useCustomerOrders(customer.id);

  if (creating) {
    return <NewOrderForm customer={customer} onDone={() => setCreating(false)} />;
  }

  return (
    <div className="customer-panel">
      <dl className="customer-panel__facts">
        <dt>{t('staff.phone')}</dt>
        <dd dir="ltr">{customer.phone || '—'}</dd>
        <dt>{t('staff.email')}</dt>
        <dd dir="ltr">{customer.email}</dd>
        <dt>{t('staff.totalSpent')}</dt>
        <dd dir="ltr">{customer.total_spent}</dd>
        <dt>{t('staff.ordersCount')}</dt>
        <dd dir="ltr">{customer.total_orders}</dd>
      </dl>

      <Button block onClick={() => setCreating(true)}>
        {t('staff.newOrder')}
      </Button>

      <section className="customer-panel__orders">
        <h3>{t('staff.recentOrders')}</h3>

        {orders.isPending ? <Spinner /> : null}

        {orders.data && orders.data.length === 0 ? (
          <StateMessage icon="🧾" title={t('staff.noOrders')} />
        ) : null}

        <ul>
          {(orders.data ?? []).map((order) => (
            <li key={order.id}>
              <code dir="ltr">{order.number}</code>
              <span>{formatDate(order.created_at, i18n.language)}</span>
              <strong dir="ltr">{order.grand_total}</strong>
              <OrderStatusBadge status={order.status} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
