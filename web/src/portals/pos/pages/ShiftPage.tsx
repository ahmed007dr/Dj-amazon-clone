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
 * الوردية: حركات الصندوق وإغلاق اليوم.
 *
 * ⚠️  **المتوقَّع لا يُعرض قبل العدّ — والخادم لا يرسله أصلًا.**
 *
 *     عرضه للكاشير يجعله يعدّ حتى يطابقه، فتصير التسوية شكلية
 *     والفرق صفرًا دائمًا. الرقم يظهر **بعد** الإغلاق، ومعه الفرق.
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

  // ⚠️  التسوية تُقرأ من نتيجة الإغلاق لا من استعلام الوردية.
  //
  //     `/session/` تعيد `null` بعد الإغلاق مباشرةً، فلا مكان
  //     آخر يحمل الفرق النقدي في تلك اللحظة.
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

          {/* ⚠️  السبب إلزامي: نقد يخرج من الدرج بلا سبب هو بالضبط
              ما يجعل فرق الإغلاق غير قابل للتفسير آخر اليوم. */}
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

            {/* ⚠️  الخروج بفعل مقصود بعد قراءة الفرق — لا تلقائيًا.
                القفز الفوري إلى بوابة وردية جديدة كان يخفي الرقم
                الذي أُغلقت الوردية من أجله. */}
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

            {/* ⚠️  خطوة تأكيد قبل الإغلاق.
                الإغلاق لا رجعة فيه: `expected_cash` يُثبَّت لقطةً
                ولا يُعاد حسابه. ضغطة واحدة بالخطأ تنهي وردية
                ما زالت تعمل — وتفتح فرقًا لا يُفسَّر. */}
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
