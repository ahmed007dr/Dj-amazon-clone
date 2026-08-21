import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCashMovements, useCloseSession, useMySession, useRecordCash } from '@/features/pos/hooks';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';

import './ShiftPage.css';

/**
 * The shift: drawer movements and closing the day.
 *
 * ⚠️  **The expected figure is not shown before the count — and the server does not send it at all.**
 *
 *     Showing it to the cashier makes them count until it matches, so the
 *     reconciliation becomes a formality and the discrepancy is always zero. The
 *     figure appears **after** closing, together with the discrepancy.
 */
export function ShiftPage() {
  const { t } = useTranslation();

  const session = useMySession();
  const movements = useCashMovements(Boolean(session.data));
  const cash = useRecordCash();
  const close = useCloseSession();

  const [kind, setKind] = useState<'PAY_IN' | 'PAY_OUT'>('PAY_IN');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');

  const [counted, setCounted] = useState('');
  const [note, setNote] = useState('');
  const [confirming, setConfirming] = useState(false);

  if (session.isPending) return <Spinner />;

  // ⚠️  The reconciliation is read from the closing result, not from the shift query.
  //
  //     `/session/` returns `null` immediately after closing, so there is no other
  //     place carrying the cash discrepancy at that moment.
  const closed = close.data ?? null;
  const error = cash.error ?? close.error;

  return (
    <div className="shift">
      <section className="shift__card">
        <h2>{t('pos.cashDrawer')}</h2>

        <div className="shift__cashform">
          <label className="shift__kind">
            {t('pos.movementKind')}
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as 'PAY_IN' | 'PAY_OUT')}
            >
              <option value="PAY_IN">{t('pos.payIn')}</option>
              <option value="PAY_OUT">{t('pos.payOut')}</option>
            </select>
          </label>

          <Field
            label={t('pos.amount')}
            type="number"
            inputMode="decimal"
            min="0.01"
            step="0.01"
            dir="ltr"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />

          {/* ⚠️  The reason is mandatory: cash leaving the drawer with no reason is exactly
              what makes the closing discrepancy unaccountable at the end of the day. */}
          <Field
            label={t('pos.reason')}
            value={reason}
            hint={t('pos.reasonHint')}
            onChange={(event) => setReason(event.target.value)}
          />

          <Button
            loading={cash.isPending}
            disabled={!amount || reason.trim().length < 3}
            onClick={() =>
              cash.mutate(
                { kind, amount, reason },
                {
                  onSuccess: () => {
                    setAmount('');
                    setReason('');
                  },
                },
              )
            }
          >
            {t('pos.record')}
          </Button>
        </div>

        <ul className="shift__movements">
          {(movements.data ?? []).map((movement) => (
            <li key={movement.id}>
              <span>{t(`pos.kind.${movement.kind}`, { defaultValue: movement.kind })}</span>
              <span dir="ltr">{movement.amount}</span>
              <span className="shift__reason truncate">{movement.reason || '—'}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="shift__card">
        <h2>{t('pos.closeShift')}</h2>

        {closed ? (
          <>
            <dl className="shift__result">
              <dt>{t('pos.expected')}</dt>
              <dd dir="ltr">{closed.expected_cash}</dd>
              <dt>{t('pos.counted')}</dt>
              <dd dir="ltr">{closed.counted_cash}</dd>
              <dt className="shift__variance">{t('pos.variance')}</dt>
              <dd className="shift__variance" dir="ltr">
                {closed.variance}
              </dd>
            </dl>

            {/* ⚠️  Leaving is a deliberate act after reading the discrepancy — not automatic.
                Jumping straight to a new shift gate used to hide the very figure
                the shift was closed for. */}
            <Button block onClick={close.finish}>
              {t('pos.doneShift')}
            </Button>
          </>
        ) : (
          <>
            <Field
              label={t('pos.countedCash')}
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              dir="ltr"
              value={counted}
              hint={t('pos.countedHint')}
              onChange={(event) => setCounted(event.target.value)}
            />

            <Field
              label={t('pos.varianceNote')}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />

            {/* ⚠️  A confirmation step before closing.
                Closing is irreversible: `expected_cash` is fixed as a snapshot
                and never recomputed. One press by mistake ends a shift that is
                still running — and opens a discrepancy that cannot be explained. */}
            {confirming ? (
              <div className="shift__confirm">
                <Alert tone="warning">{t('pos.closeWarning')}</Alert>
                <div className="shift__confirm-actions">
                  <Button variant="secondary" onClick={() => setConfirming(false)}>
                    {t('common.cancel')}
                  </Button>
                  <Button
                    variant="danger"
                    loading={close.isPending}
                    onClick={() => close.mutate({ counted, note })}
                  >
                    {t('pos.confirmClose')}
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                block
                disabled={counted === ''}
                onClick={() => setConfirming(true)}
              >
                {t('pos.closeShift')}
              </Button>
            )}
          </>
        )}

        {error ? (
          <Alert tone="danger">
            {isApiError(error) ? error.displayMessage : t('state.errorTitle')}
          </Alert>
        ) : null}
      </section>
    </div>
  );
}
