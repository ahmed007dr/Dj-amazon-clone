import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatMoney } from '@/shared/utils/format';

import { useShippingQuotes } from '../hooks';

import './OptionList.css';

/**
 * اختيار طريقة الشحن.
 *
 * ⚠️  الرسوم من الخادم عند كل تغيير محافظة — لا جدول محلي.
 *
 *     الشحن المجاني فوق حدّ يختلف بالمنطقة، والرسوم تُعدَّل من لوحة
 *     الأدمن. جدول في الواجهة يجعل تعديل الأدمن بلا أثر حتى النشر،
 *     ويعرض للعميل رقمًا يخالف فاتورته.
 */
export function ShippingPicker({
  governorate,
  subtotal,
  value,
  onChange,
}: {
  governorate: string;
  subtotal: string;
  value: string | null;
  onChange: (methodCode: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { data: quotes, isPending, error } = useShippingQuotes(governorate, subtotal);

  if (!governorate) {
    return <p className="muted">{t('checkout.pickAddressFirst')}</p>;
  }

  if (isPending) return <Spinner />;
  if (error) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (quotes.length === 0) {
    // ⚠️  محافظة بلا طريقة شحن حالة حقيقية (منطقة نائية بلا سريع)
    return <StateMessage icon="⌀" title={t('checkout.noShipping')} />;
  }

  return (
    <div className="option-list" role="radiogroup" aria-label={t('checkout.shipping')}>
      {quotes.map((quote) => (
        <label
          key={quote.method_code}
          className={`option ${value === quote.method_code ? 'is-selected' : ''}`}
        >
          <input
            type="radio"
            name="shipping"
            value={quote.method_code}
            checked={value === quote.method_code}
            onChange={() => {
              onChange(quote.method_code);
            }}
          />

          <span className="option__label">{localized(quote, 'method_name')}</span>

          <span className="option__meta">
            {Number.parseFloat(quote.fee) === 0
              ? t('checkout.freeShipping')
              : formatMoney(quote.fee, i18n.language)}
          </span>
        </label>
      ))}
    </div>
  );
}
