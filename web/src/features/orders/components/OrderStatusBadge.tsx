import { useTranslation } from 'react-i18next';

import { Badge } from '@/shared/ui/Badge';

import type { OrderStatus, PaymentStatus } from '../types';

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

const ORDER_TONES: Record<OrderStatus, Tone> = {
  PENDING: 'warning',
  CONFIRMED: 'info',
  PROCESSING: 'info',
  SHIPPED: 'info',
  DELIVERED: 'success',
  COMPLETED: 'success',
  CANCELLED: 'danger',
  REFUNDED: 'neutral',
};

const PAYMENT_TONES: Record<PaymentStatus, Tone> = {
  UNPAID: 'warning',
  PENDING: 'warning',
  PAID: 'success',
  PARTIALLY_REFUNDED: 'neutral',
  REFUNDED: 'neutral',
  FAILED: 'danger',
};

/**
 * ⚠️  شارتان لا واحدة.
 *
 *     حالة الطلب وحالة الدفع مستقلتان: «مؤكد · غير مدفوع» حالة
 *     يومية في الدفع عند الاستلام. دمجهما في شارة واحدة يجعل نصف
 *     الحالات الحقيقية غير قابلة للعرض.
 */
export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const { t } = useTranslation();
  return <Badge tone={ORDER_TONES[status]}>{t(`orderStatus.${status}`)}</Badge>;
}

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  const { t } = useTranslation();
  return <Badge tone={PAYMENT_TONES[status]}>{t(`paymentStatus.${status}`)}</Badge>;
}
