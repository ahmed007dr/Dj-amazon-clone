import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import { useCancelOrder } from '../hooks';

import './CancelOrderButton.css';

/**
 * إلغاء الطلب.
 *
 * ⚠️  **السبب مطلوب** — والخادم يشترطه بثلاثة محارف على الأقل.
 *
 *     ليس بيروقراطية: الإلغاء يُفرج عن المخزون ويترك أثرًا في
 *     السجل، و«لماذا أُلغيت هذه الطلبات؟» سؤال يُسأل شهريًا. حقل
 *     فارغ يجعل الجواب مستحيلًا رجعيًا.
 *
 * ⚠️  وزر الإلغاء يظهر حسب `can_cancel` **من الخادم** لا حسب قائمة
 *     حالات في الواجهة: الثانية تتباعد عن آلة الحالة الحقيقية،
 *     فيظهر زر يفشل عند الضغط.
 */
export function CancelOrderButton({ orderId }: { orderId: string }) {
  const { t } = useTranslation();
  const cancelOrder = useCancelOrder();

  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <Button
        variant="secondary"
        onClick={() => {
          setOpen(true);
        }}
      >
        {t('orders.cancel')}
      </Button>
    );
  }

  return (
    <div className="cancel-order">
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <label className="cancel-order__label" htmlFor="cancel-reason">
        {t('orders.cancelReason')}
      </label>
      <textarea
        id="cancel-reason"
        className="cancel-order__input"
        rows={2}
        minLength={3}
        maxLength={500}
        value={reason}
        placeholder={t('orders.cancelReasonPlaceholder')}
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />

      <div className="cancel-order__actions">
        <Button
          variant="danger"
          loading={cancelOrder.isPending}
          disabled={reason.trim().length < 3}
          onClick={() => {
            setError(null);
            cancelOrder.mutate(
              { id: orderId, reason: reason.trim() },
              {
                onSuccess: () => {
                  setOpen(false);
                },
                onError: (cause) => {
                  setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
                },
              },
            );
          }}
        >
          {t('orders.confirmCancel')}
        </Button>

        <Button
          variant="ghost"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
        >
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
