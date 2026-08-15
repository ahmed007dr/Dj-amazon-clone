import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { PaymentInput } from '@/features/pos/api';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import './PaymentPanel.css';

/**
 * تحصيل البيعة.
 *
 * ⚠️  **الخادم يرفض ما لا يساوي الإجمالي بالضبط.**
 *
 *     الأقل بيعة غير مسدَّدة تُسجَّل كمكتملة؛ والأكثر فائض لا يعرف
 *     النظام أين يذهب. لذلك الباقي للعميل يُحسب هنا ولا يُرسَل:
 *     المسجَّل هو ثمن البضاعة، والفكّة تخرج من الدرج فورًا.
 *
 * ⚠️  و«المبلغ المستلم» يخصّ النقد وحده.
 *
 *     البطاقة تُمرَّر بالقيمة بالضبط على الطرفية — لا باقي فيها،
 *     وحقل استلام لها يدعو إلى خطأ إدخال بلا أي فائدة.
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

  // ⚠️  الحساب بأرقام عشرية للعرض فقط — لا يُرسَل منه شيء.
  //     المبالغ المرسلة نصوص، والخادم هو مرجع كل مقارنة.
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
      // ⚠️  **المستحق لا المستلم.**
      //
      //     إرسال ما في يد الكاشير يجعل الفكّة تُسجَّل كإيراد،
      //     فيُظهر الدرج فائضًا يساوي كل باقٍ أعطاه اليوم.
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

          {/* ⚠️  الباقي بخط كبير: هو الرقم الوحيد الذي يُقرأ بسرعة
              أثناء تسليم النقد، وقراءته خطأً تعني عجزًا في الدرج. */}
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
