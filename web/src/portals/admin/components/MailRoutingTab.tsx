import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteMailRoute,
  useMailAccounts,
  useMailRoutes,
  useRoutingMap,
  useSaveMailRoute,
  type MailPurpose,
  type RoutingRow,
  type RoutingSource,
} from '@/features/mailing/adminApi';
import { isApiError } from '@/shared/http';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './MailRoutingTab.css';

const PURPOSES: MailPurpose[] = [
  'ACCOUNT',
  'ORDERS',
  'PAYMENTS',
  'SHIPPING',
  'INVENTORY',
  'MARKETING',
  'SUPPORT',
  'REPORTS',
  'SYSTEM',
];

/**
 * ⚠️  المصدر يُلوَّن ويُسمّى.
 *
 *     «مُسنَد» و«ساقط إلى الافتراضي» يعطيان نفس الحساب اليوم
 *     ويختلفان غدًا: تغيير الافتراضي يحرّك كل ما لم يُسنَد صراحةً.
 *     شاشة تعرض النتيجة وحدها تُخفي هذا الفرق حتى يقع.
 */
const SOURCE_TONE: Record<RoutingSource, 'success' | 'info' | 'neutral' | 'warning'> = {
  template: 'success',
  purpose: 'success',
  default: 'info',
  priority: 'neutral',
  env: 'warning',
};

export function MailRoutingTab() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const accounts = useMailAccounts();
  const routes = useMailRoutes();
  const routing = useRoutingMap();

  const saveRoute = useSaveMailRoute();
  const removeRoute = useDeleteMailRoute();

  const [purpose, setPurpose] = useState<MailPurpose>('ORDERS');
  const [accountId, setAccountId] = useState('');

  const sendingAccounts = (accounts.data ?? []).filter(
    (account) => account.direction !== 'IN' && account.is_active,
  );

  const assign = () => {
    if (!accountId) return;

    const existing = (routes.data ?? []).find(
      (route) => route.purpose === purpose && !route.template_key,
    );

    saveRoute.mutate(
      {
        ...(existing ? { id: existing.id } : {}),
        body: { purpose, template_key: '', account: accountId, is_active: true },
      },
      {
        onSuccess: () => notify(t('mail.routeSaved'), 'success'),
        onError: (cause) =>
          // ⚠️  الرسالة من الخادم لا رسالة عامة: هنا يقع رفض إسناد
          //     رسائل الأمان إلى حساب تسويقي، وسببه هو المعلومة.
          notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  const columns: Column<RoutingRow>[] = [
    {
      key: 'template',
      header: t('mail.template'),
      render: (row) => (
        <div className="routing__template">
          <code>{row.template_key}</code>
          <small>{row.subject_ar}</small>
        </div>
      ),
    },
    {
      key: 'purpose',
      header: t('mail.purpose'),
      secondary: true,
      render: (row) => t(`mail.purpose_${row.purpose}`),
    },
    {
      key: 'account',
      header: t('mail.account'),
      render: (row) =>
        row.account_code ? (
          <span>{row.account_label_ar}</span>
        ) : (
          <span className="routing__none">{t('mail.noAccount')}</span>
        ),
    },
    {
      key: 'source',
      header: t('mail.source'),
      render: (row) => <Badge tone={SOURCE_TONE[row.source]}>{t(`mail.source_${row.source}`)}</Badge>,
    },
  ];

  return (
    <div className="routing">
      <Alert tone="info">{t('mail.routingHint')}</Alert>

      <div className="routing__assign">
        <label className="routing__field">
          <span>{t('mail.purpose')}</span>
          <select value={purpose} onChange={(event) => setPurpose(event.target.value as MailPurpose)}>
            {PURPOSES.map((value) => (
              <option key={value} value={value}>
                {t(`mail.purpose_${value}`)}
              </option>
            ))}
          </select>
        </label>

        <label className="routing__field">
          <span>{t('mail.account')}</span>
          <select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">{t('mail.pickAccount')}</option>
            {sendingAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.label_ar}
                {account.is_marketing ? ` — ${t('mail.isMarketing')}` : ''}
              </option>
            ))}
          </select>
        </label>

        <Button onClick={assign} loading={saveRoute.isPending} disabled={!accountId}>
          {t('mail.assign')}
        </Button>
      </div>

      {(routes.data ?? []).length > 0 ? (
        <ul className="routing__rules">
          {(routes.data ?? []).map((route) => (
            <li key={route.id}>
              <span>
                {t(`mail.purpose_${route.purpose}`)}
                {route.template_key ? ` · ${route.template_key}` : ''}
              </span>
              <span className="routing__arrow" aria-hidden="true">
                ←
              </span>
              <span>{route.account_label_ar}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  removeRoute.mutate(route.id, {
                    onSuccess: () => notify(t('mail.routeRemoved'), 'success'),
                  })
                }
              >
                {t('action.delete')}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}

      <DataTable
        columns={columns}
        rows={routing.data ?? []}
        rowKey={(row) => row.template_key}
        isLoading={routing.isPending}
        error={routing.error}
        emptyTitle={t('mail.noTemplates')}
      />
    </div>
  );
}
