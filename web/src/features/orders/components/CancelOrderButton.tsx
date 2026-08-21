import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import { useCancelOrder } from '../hooks';

import './CancelOrderButton.css';

/**
 * Cancelling the order.
 *
 * ⚠️  **A reason is required** — and the server demands at least three characters.
 *
 *     This is not bureaucracy: cancellation releases the stock and leaves a
 *     trace in the log, and "why were these orders cancelled?" is a question
 *     asked monthly. An empty field makes the answer retrospectively impossible.
 *
 * ⚠️  And the cancel button appears according to `can_cancel` **from the
 *     server**, not according to a list of statuses in the frontend: the latter
 *     drifts from the real state machine, so a button appears and fails when pressed.
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
