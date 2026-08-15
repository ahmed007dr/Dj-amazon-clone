import { useTranslation } from 'react-i18next';

import type { OrderDetail } from '@/features/orders/types';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Button } from '@/shared/ui/Button';

import './Receipt.css';

/**
 * إيصال البيعة.
 *
 * ⚠️  **كل رقم من الطلب المخزَّن — لا حساب هنا.**
 *
 *     الطلب يحمل لقطة وقت البيع (ADR-30): السعر والضريبة والخصم
 *     كما كانت في تلك اللحظة. إعادة حسابها للطباعة تنتج ورقة
 *     تخالف السجل، والفارق يظهر عند أول مرتجع.
 *
 * ⚠️  والطباعة `window.print` بأنماط `@media print` — لا مكتبة.
 *
 *     طابعة الإيصالات على الكاونتر طابعة نظام عادية. إدخال مكتبة
 *     توليد PDF يضيف حزمة ثقيلة لجهاز لوحي مقابل خطوة إضافية
 *     (تنزيل ثم فتح ثم طباعة) في كل بيعة.
 */
export function Receipt({
  order,
  onDone,
}: {
  order: OrderDetail;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  return (
    <div className="receipt">
      <div className="receipt__paper">
        <h2 className="receipt__number">{order.number}</h2>
        <p className="receipt__date">{new Date(order.created_at).toLocaleString()}</p>

        <table className="receipt__lines">
          <tbody>
            {order.lines.map((line) => (
              <tr key={line.id}>
                <td>{localized(line, 'product_name')}</td>

                <td dir="ltr">×{line.quantity}</td>
                <td dir="ltr">{line.total}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="receipt__totals">
          <dt>{t('orders.subtotal')}</dt>
          <dd dir="ltr">{order.subtotal}</dd>

          {/* ⚠️  الضريبة **تُخفى حين تكون صفرًا** لا تُعرض «٠.٠٠».
              نسبتها متغيّرة وقد تغيب عن صنف أو عن المتجر كله؛
              وسطر بصفر يجعل العميل يسأل عن ضريبة لم تُحصَّل. */}
          {Number(order.tax_total) > 0 ? (
            <>
              <dt>{t('orders.tax')}</dt>
              <dd dir="ltr">{order.tax_total}</dd>
            </>
          ) : null}

          {Number(order.discount_total) > 0 ? (
            <>
              <dt>{t('orders.discount')}</dt>
              <dd dir="ltr">−{order.discount_total}</dd>
            </>
          ) : null}

          <dt className="receipt__grand">{t('pos.total')}</dt>
          <dd className="receipt__grand" dir="ltr">
            {order.grand_total}
          </dd>
        </dl>
      </div>

      <div className="receipt__actions">
        {/* ⚠️  إعادة الطباعة متاحة ما دام الإيصال معروضًا: أول
            طباعة تفشل لورق ناقص أو طابعة نائمة أكثر مما يُتوقَّع. */}
        <Button variant="secondary" onClick={() => window.print()}>
          {t('pos.print')}
        </Button>
        <Button onClick={onDone}>{t('pos.newSale')}</Button>
      </div>
    </div>
  );
}
