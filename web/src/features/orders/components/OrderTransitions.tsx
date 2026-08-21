import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import { useCompleteOrder, useTransitionOrder } from '../adminHooks';
import type { OrderStatus } from '../types';

import './OrderTransitions.css';

/**
 * ⚠️  **A copy of the state machine on the server** — for display only.
 *
 *     The server refuses any disallowed transition with `409` regardless of
 *     this map; its presence here prevents showing a button that fails when
 *     pressed. And when the two drift apart the server remains the truth — the
 *     extra button is refused with a clear message rather than obscure behaviour.
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

    // ⚠️  "Complete" is a separate endpoint: it emits the `order_completed` event
    //     that finance, loyalty and commissions later build on.
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
