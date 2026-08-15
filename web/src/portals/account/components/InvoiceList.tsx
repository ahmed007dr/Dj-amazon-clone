import { useTranslation } from 'react-i18next';

import type { Invoice } from '@/features/b2b/api';
import { Badge } from '@/shared/ui/Badge';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate } from '@/shared/utils/format';

import './InvoiceList.css';

const TONE: Record<string, 'success' | 'danger' | 'info' | 'neutral'> = {
  PAID: 'success',
  OVERDUE: 'danger',
  ISSUED: 'info',
  CANCELLED: 'neutral',
};

/**
 * فواتير العميل.
 *
 * ⚠️  **`is_overdue` المحسوب لا `status` المخزَّنة.**
 *
 *     الحالة تُحدَّث بمهمة دورية؛ وأي تعطّل فيها يجعل فاتورة
 *     تجاوزت استحقاقها بأسبوع تظهر «صادرة» بهدوء. الخادم يحسب
 *     التأخر لحظيًا، والواجهة تعرض ما حسبه.
 */
export function InvoiceList({ invoices }: { invoices: Invoice[] }) {
  const { t, i18n } = useTranslation();

  if (invoices.length === 0) {
    return <StateMessage icon="🧾" title={t('b2b.noInvoices')} />;
  }

  return (
    <ul className="invoice-list">
      {invoices.map((invoice) => (
        <li key={invoice.id} className={invoice.is_overdue ? 'is-overdue' : ''}>
          <div className="invoice-list__main">
            <code className="invoice-list__number">{invoice.number}</code>
            <span className="invoice-list__order">{invoice.order_number}</span>
          </div>

          <div className="invoice-list__dates">
            <span>{formatDate(invoice.issued_on, i18n.language)}</span>
            <span className="invoice-list__due">
              {t('b2b.dueOn')} {formatDate(invoice.due_on, i18n.language)}
              {invoice.is_overdue ? (
                <strong> · {t('b2b.daysLate', { count: invoice.days_overdue })}</strong>
              ) : null}
            </span>
          </div>

          <strong className="invoice-list__total" dir="ltr">
            {invoice.total}
          </strong>

          <Badge tone={TONE[invoice.status] ?? 'info'}>
            {t(`b2b.invoiceStatus.${invoice.status}`)}
          </Badge>
        </li>
      ))}
    </ul>
  );
}
