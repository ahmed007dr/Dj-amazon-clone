import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { usePaymentMethods } from '../hooks';

import './OptionList.css';

/**
 * اختيار طريقة الدفع.
 *
 * ⚠️  القائمة تأتي من `/payments/methods/` وتُحسب من البوابات
 *     **المفعّلة الآن**. (ADR-15)
 *
 *     الأدمن يوقف بوابة فتختفي من هنا في الطلب التالي بلا نشر.
 *     قائمة ثابتة في الواجهة تعرض بوابة موقوفة، فيختارها العميل
 *     ويفشل دفعه بعد أن أدخل بياناته.
 */
export function PaymentPicker({
  amount,
  value,
  onChange,
}: {
  amount: string;
  value: string | null;
  onChange: (method: string) => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { data: methods, isPending, error } = usePaymentMethods(amount);

  if (isPending) return <Spinner />;
  if (error) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (methods.length === 0) {
    // ⚠️  حالة حقيقية: كل البوابات موقوفة أو المبلغ خارج حدودها
    return <StateMessage icon="⌀" title={t('checkout.noPayment')} body={t('checkout.noPaymentHint')} />;
  }

  return (
    <div className="option-list" role="radiogroup" aria-label={t('checkout.payment')}>
      {methods.map((option) => (
        <label
          key={option.method}
          className={`option ${value === option.method ? 'is-selected' : ''}`}
        >
          <input
            type="radio"
            name="payment"
            value={option.method}
            checked={value === option.method}
            onChange={() => {
              onChange(option.method);
            }}
          />

          <span className="option__label">{localized(option, 'label')}</span>

          <span className="option__meta muted">{localized(option, 'provider_name')}</span>
        </label>
      ))}
    </div>
  );
}
