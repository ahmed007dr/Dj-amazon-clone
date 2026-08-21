import { useTranslation } from 'react-i18next';

import { Alert } from '@/shared/ui/Alert';

import type { LineIssue } from '../types';

import './CartIssues.css';

/**
 * Cart problems.
 *
 * ⚠️  Shown **before** the lines, not after them.
 *
 *     A customer who cannot check out needs to know why in the first thing they
 *     see. Putting it below a long list means they press "checkout" and are
 *     refused with no understanding.
 *
 * ⚠️  And the message arrives translated from the server — we do not rebuild it
 *     from `code`.
 *
 *     Rebuilding means a list of codes maintained in two repositories, and one
 *     new code appearing to the customer as raw English text.
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
