import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdminStatement,
  useGrantCredit,
  useRecordPayment,
  useSuspendCredit,
  type BusinessProfile,
} from '@/features/b2b/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './CreditPanel.css';

/**
 * إدارة ائتمان عميل.
 *
 * ⚠️  **الرصيد الحالي معروض قبل حقول المنح.**
 *
 *     رفع الحد قرار يُتخذ على ضوء ما على العميل الآن وما تأخّر
 *     منه. نموذج فارغ بلا سياق يجعل القرار يُتخذ على الاسم فقط.
 *
 * ⚠️  والإيقاف بخطوة تأكيد.
 *
 *     ضغطة واحدة تمنع صيدلية من الشراء فورًا — وقد تكون في وسط
 *     طلب. السبب إلزامي لأنه ما سيُقال لها حين تتصل.
 */
export function CreditPanel({ business }: { business: BusinessProfile }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const statement = useAdminStatement(business.id);
  const grant = useGrantCredit();
  const suspend = useSuspendCredit();
  const payment = useRecordPayment();

  const [limit, setLimit] = useState(business.credit_limit);
  const [terms, setTerms] = useState(String(business.payment_terms_days));
  const [note, setNote] = useState('');

  const [amount, setAmount] = useState('');
  const [reference, setReference] = useState('');

  const [confirmingSuspend, setConfirmingSuspend] = useState(false);
  const [reason, setReason] = useState('');

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const done = (message: string) => () => notify(message, 'success');

  return (
    <div className="credit-panel">
      {statement.isPending ? (
        <Spinner />
      ) : statement.data ? (
        <dl className="credit-panel__figures">
          <dt>{t('b2b.outstanding')}</dt>
          <dd dir="ltr">{statement.data.outstanding}</dd>
          <dt>{t('b2b.creditLimit')}</dt>
          <dd dir="ltr">{statement.data.credit_limit}</dd>
          <dt>{t('b2b.closingBalance')}</dt>
          <dd dir="ltr">{statement.data.closing_balance}</dd>
        </dl>
      ) : null}

      {statement.data ? (
        <div className="credit-panel__aging">
          {statement.data.aging.map((bucket) => (
            <div key={bucket.label}>
              <span>{t(`b2b.aging.${bucket.label}`, { defaultValue: bucket.label })}</span>
              <strong dir="ltr">{bucket.amount}</strong>
            </div>
          ))}
        </div>
      ) : null}

      <section className="credit-panel__section">
        <h3>{t('b2b.grantCredit')}</h3>

        <Field
          label={t('b2b.creditLimit')}
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          dir="ltr"
          value={limit}
          onChange={(event) => setLimit(event.target.value)}
        />
        <Field
          label={t('b2b.terms')}
          type="number"
          inputMode="numeric"
          min="0"
          max="365"
          dir="ltr"
          value={terms}
          hint={t('b2b.termsHint')}
          onChange={(event) => setTerms(event.target.value)}
        />
        <Field
          label={t('b2b.note')}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />

        <Button
          block
          loading={grant.isPending}
          onClick={() =>
            grant.mutate(
              { id: business.id, limit, terms_days: Number(terms) || 0, note },
              { onSuccess: done(t('b2b.creditGranted')), onError: fail },
            )
          }
        >
          {t('b2b.saveCredit')}
        </Button>
      </section>

      <section className="credit-panel__section">
        <h3>{t('b2b.recordPayment')}</h3>

        <Field
          label={t('b2b.amount')}
          type="number"
          inputMode="decimal"
          min="0.01"
          step="0.01"
          dir="ltr"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
        <Field
          label={t('b2b.reference')}
          value={reference}
          hint={t('b2b.referenceHint')}
          onChange={(event) => setReference(event.target.value)}
        />

        <Button
          block
          variant="secondary"
          loading={payment.isPending}
          disabled={amount === ''}
          onClick={() =>
            payment.mutate(
              { id: business.id, amount, reference },
              {
                onSuccess: () => {
                  setAmount('');
                  setReference('');
                  notify(t('b2b.paymentRecorded'), 'success');
                },
                onError: fail,
              },
            )
          }
        >
          {t('b2b.savePayment')}
        </Button>
      </section>

      <section className="credit-panel__section">
        <h3>{t('b2b.suspendCredit')}</h3>

        {confirmingSuspend ? (
          <>
            <Alert tone="warning">{t('b2b.suspendWarning')}</Alert>
            <Field
              label={t('b2b.suspendReason')}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <div className="credit-panel__confirm">
              <Button variant="secondary" onClick={() => setConfirmingSuspend(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                variant="danger"
                loading={suspend.isPending}
                disabled={reason.trim().length < 3}
                onClick={() =>
                  suspend.mutate(
                    { id: business.id, reason },
                    {
                      onSuccess: () => {
                        setConfirmingSuspend(false);
                        setReason('');
                        notify(t('b2b.creditSuspended'), 'success');
                      },
                      onError: fail,
                    },
                  )
                }
              >
                {t('b2b.confirmSuspend')}
              </Button>
            </div>
          </>
        ) : (
          <Button block variant="ghost" onClick={() => setConfirmingSuspend(true)}>
            {t('b2b.suspendCredit')}
          </Button>
        )}
      </section>
    </div>
  );
}
