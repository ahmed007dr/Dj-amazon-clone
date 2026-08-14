import { useTranslation } from 'react-i18next';

import { Alert } from '@/shared/ui/Alert';

import type { LineIssue } from '../types';

import './CartIssues.css';

/**
 * مشاكل السلة.
 *
 * ⚠️  تُعرض **قبل** الأسطر لا بعدها.
 *
 *     العميل الذي لا يستطيع إتمام الشراء يحتاج أن يعرف السبب في
 *     أول شيء يراه. وضعها أسفل قائمة طويلة يعني أنه يضغط «إتمام»
 *     ويُرفض بلا أن يفهم.
 *
 * ⚠️  والرسالة تأتي من الخادم مترجَمة — لا نُعيد بناءها من `code`.
 *
 *     إعادة البناء تعني قائمة رموز تُحدَّث في مستودعين، ورمزًا
 *     جديدًا واحدًا يظهر للعميل كنص إنجليزي خام.
 */
export function CartIssues({ issues }: { issues: LineIssue[] }) {
  const { t } = useTranslation();

  if (issues.length === 0) return null;

  return (
    <Alert tone="warning">
      <p className="cart-issues__title">{t('cart.issuesTitle')}</p>
      <ul className="cart-issues__list">
        {issues.map((issue) => (
          <li key={`${issue.line_id}-${issue.code}`}>
            <strong>{issue.product_name}</strong> — {issue.message}
            {issue.available !== null ? ` (${t('cart.availableNow', { count: issue.available })})` : null}
          </li>
        ))}
      </ul>
    </Alert>
  );
}
