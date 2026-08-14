import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import { useCompleteOrder, useTransitionOrder } from '../adminHooks';
import type { OrderStatus } from '../types';

import './OrderTransitions.css';

/**
 * ⚠️  **نسخة من آلة الحالة في الخادم** — للعرض فقط.
 *
 *     الخادم يرفض أي انتقال غير مسموح بـ `409` بصرف النظر عن هذه
 *     الخريطة؛ ووجودها هنا يمنع عرض زر يفشل عند الضغط. وحين
 *     تتباعد الاثنتان يبقى الخادم هو الحقيقة — والزر الزائد يُرفض
 *     برسالة واضحة لا بسلوك غامض.
 */
const NEXT_STATES: Record<OrderStatus, OrderStatus[]> = {
  PENDING: ['CONFIRMED', 'CANCELLED'],
  CONFIRMED: ['PROCESSING', 'CANCELLED'],
  PROCESSING: ['SHIPPED', 'CANCELLED'],
  SHIPPED: ['DELIVERED', 'CANCELLED'],
  DELIVERED: ['COMPLETED', 'REFUNDED'],
  COMPLETED: ['REFUNDED'],
  CANCELLED: [],
  REFUNDED: [],
};

export function OrderTransitions({
  orderId,
  status,
}: {
  orderId: string;
  status: OrderStatus;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const transition = useTransitionOrder();
  const complete = useCompleteOrder();

  const targets = NEXT_STATES[status];
  if (targets.length === 0) {
    return <p className="muted">{t('admin.finalState')}</p>;
  }

  function run(target: OrderStatus) {
    const onError = (cause: unknown) => {
      notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
    };
    const onSuccess = () => {
      notify(t('admin.statusChanged', { status: t(`orderStatus.${target}`) }));
    };

    // ⚠️  «إكمال» نقطة نهاية منفصلة: تُطلق حدث `order_completed`
    //     الذي تبني عليه المالية والولاء والعمولات لاحقًا.
    if (target === 'COMPLETED') {
      complete.mutate(orderId, { onSuccess, onError });
      return;
    }

    transition.mutate({ id: orderId, status: target }, { onSuccess, onError });
  }

  const pending = transition.isPending || complete.isPending;

  return (
    <div className="order-transitions">
      {targets.map((target) => (
        <Button
          key={target}
          variant={target === 'CANCELLED' || target === 'REFUNDED' ? 'secondary' : 'primary'}
          disabled={pending}
          onClick={() => {
            run(target);
          }}
        >
          {t(`admin.moveTo.${target}`)}
        </Button>
      ))}
    </div>
  );
}
