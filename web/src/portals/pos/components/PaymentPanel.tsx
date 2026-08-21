import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { PaymentInput } from '@/features/pos/api';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import './PaymentPanel.css';

/**
 * Charging the sale.
 *
 * ⚠️  **The server refuses anything not exactly equal to the total.**
 *
 *     Less is an unsettled sale recorded as complete; more is a surplus the
 *     system does not know where to put. So the customer's change is computed
 *     here and never sent: what is recorded is the price of the goods, and the
 *     change leaves the drawer immediately.
 *
 * ⚠️  And "amount received" applies to cash alone.
 *
 *     A card is charged for the exact value at the terminal — there is no
 *     change in it, and a received-amount field for it invites a data-entry
 *     error with no benefit whatsoever.
 */
export function PaymentPanel({
  total,
  disabled,
  pending,
  onSubmit,
}: {
  total: string;
  disabled: boolean;
  pending: boolean;
  onSubmit: (payments: PaymentInput[]) => void;
}) {
  const { t, i18n } = useTranslation();

  const [split, setSplit] = useState(false);
  const [cardAmount, setCardAmount] = useState('');
  const [received, setReceived] = useState('');

  const totalNumber = Number(total || '0');
  const cardNumber = Number(cardAmount || '0');

  // ⚠️  The arithmetic uses decimals for display only — nothing from it is sent.
  //     The amounts sent are strings, and the server is the reference for every comparison.
  const cashDue = useMemo(
    () => Math.max(totalNumber - (split ? cardNumber : 0), 0),
    [totalNumber, split, cardNumber],
  );

  const change = useMemo(() => {
    const paid = Number(received || '0');
    return paid > cashDue ? paid - cashDue : 0;
  }, [received, cashDue]);

  const cardExceedsTotal = split && cardNumber > totalNumber;

  const submit = () => {
    const payments: PaymentInput[] = [];

    if (split && cardNumber > 0) {
      payments.push({ method: 'CARD', amount: cardAmount });
    }
    if (cashDue > 0) {
      // ⚠️  **What is due, not what was received.**
      //
      //     Sending what is in the cashier's hand records the change as revenue,
      //     so the drawer shows a surplus equal to all the change they gave that day.
      payments.push({ method: 'CASH', amount: cashDue.toFixed(2) });
    }

    onSubmit(payments);
  };

  return (
    <div className="pay-panel">
      <div className="pay-panel__total">
        <span>{t('pos.total')}</span>
        <strong dir="ltr">{total}</strong>
      </div>

      <label className="pay-panel__split">
        <input
          type="checkbox"
          checked={split}
          onChange={(event) => {
            setSplit(event.target.checked);
            if (!event.target.checked) setCardAmount('');
          }}
        />
        {t('pos.splitPayment')}
      </label>

      {split ? (
        <label className="pay-panel__field">
          {t('pos.cardAmount')}
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="0.01"
            dir="ltr"
            value={cardAmount}
            onChange={(event) => setCardAmount(event.target.value)}
          />
        </label>
      ) : null}

      {cashDue > 0 ? (
        <>
          <div className="pay-panel__due">
            <span>{t('pos.cashDue')}</span>
            <strong dir="ltr">{cashDue.toFixed(2)}</strong>
          </div>

          <label className="pay-panel__field">
            {t('pos.received')}
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              dir="ltr"
              value={received}
              onChange={(event) => setReceived(event.target.value)}
            />
          </label>

          {/* ⚠️  The change in a large font: it is the one figure read quickly
              while handing over cash, and misreading it means a shortfall in the drawer. */}
          {change > 0 ? (
            <div className="pay-panel__change">
              <span>{t('pos.change')}</span>
              <strong dir="ltr">
                {change.toLocaleString(i18n.language, { minimumFractionDigits: 2 })}
              </strong>
            </div>
          ) : null}
        </>
      ) : null}

      {cardExceedsTotal ? <Alert tone="warning">{t('pos.cardOverTotal')}</Alert> : null}

      <Button
        block
        size="lg"
        loading={pending}
        disabled={disabled || cardExceedsTotal}
        onClick={submit}
      >
        {t('pos.collect')}
      </Button>
    </div>
  );
}
