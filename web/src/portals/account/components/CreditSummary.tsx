import { useTranslation } from 'react-i18next';

import type { AccountSummary } from '@/features/b2b/api';

import './CreditSummary.css';

/**
 * ملخّص الائتمان.
 *
 * ⚠️  **المتاح هو الرقم الأكبر على الشاشة.**
 *
 *     صاحب الصيدلية يبني طلبه على «كم أستطيع أن أشتري الآن» لا
 *     على حدّه الكلي. إبرازهما بنفس الوزن يجعله يخطّط على رقم
 *     ثم يُرفض عند الإتمام.
 *
 * ⚠️  والشريط يمتلئ باتجاه الخطر لا باتجاه الإنجاز.
 *
 *     شريط تقدّم يمتلئ عادةً يعني نجاحًا؛ وهنا يعني اقترابًا من
 *     السقف. اللون يتدرّج مع الامتلاء ليقرأ المعنى الصحيح.
 */
export function CreditSummary({ account }: { account: AccountSummary }) {
  const { t } = useTranslation();

  const limit = Number(account.credit_limit);
  const outstanding = Number(account.outstanding);

  // ⚠️  حارس القسمة على صفر: حساب بلا ائتمان حده صفر.
  const usedPercent = limit > 0 ? Math.min((outstanding / limit) * 100, 100) : 0;
  const tone = usedPercent >= 90 ? 'is-critical' : usedPercent >= 70 ? 'is-warning' : '';

  return (
    <section className="credit-summary">
      <div className="credit-summary__head">
        <h2 className="credit-summary__name">{account.legal_name}</h2>
        <span className={`credit-summary__status is-${account.credit_status.toLowerCase()}`}>
          {t(`b2b.creditStatus.${account.credit_status}`)}
        </span>
      </div>

      <div className="credit-summary__figures">
        <div className="credit-summary__available">
          <span>{t('b2b.available')}</span>
          <strong dir="ltr">{account.available}</strong>
        </div>

        <dl className="credit-summary__meta">
          <dt>{t('b2b.outstanding')}</dt>
          <dd dir="ltr">{account.outstanding}</dd>
          <dt>{t('b2b.creditLimit')}</dt>
          <dd dir="ltr">{account.credit_limit}</dd>
          <dt>{t('b2b.terms')}</dt>
          <dd>{t('b2b.termsDays', { count: account.payment_terms_days })}</dd>
        </dl>
      </div>

      {limit > 0 ? (
        <div
          className={`credit-summary__bar ${tone}`}
          role="meter"
          aria-valuenow={Math.round(usedPercent)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={t('b2b.usedPercent')}
        >
          <span style={{ inlineSize: `${usedPercent}%` }} />
        </div>
      ) : null}
    </section>
  );
}
