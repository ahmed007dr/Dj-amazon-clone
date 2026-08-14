import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  listProviders,
  toggleProvider,
  type PaymentProvider,
} from '@/features/payments/adminApi';
import { isApiError } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './AdminPaymentsPage.css';

const KEY = ['admin', 'payment-providers'] as const;

/**
 * بوابات الدفع.
 *
 * ⚠️  التشغيل والإيقاف **أثره فوري بلا إعادة نشر** — وهذا جوهر
 *     ADR-15: البوابات بيانات والمحوّلات كود.
 */
export function AdminPaymentsPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [reasons, setReasons] = useState<Record<string, string>>({});

  const providers = useQuery({ queryKey: KEY, queryFn: listProviders });

  const toggle = useMutation({
    mutationFn: (args: { id: string; isActive: boolean; reason: string }) =>
      toggleProvider(args.id, args.isActive, args.reason),
    onSuccess: (provider) => {
      notify(
        provider.is_active
          ? t('admin.gatewayEnabled', { name: provider.code })
          : t('admin.gatewayDisabled', { name: provider.code }),
      );
      void queryClient.invalidateQueries({ queryKey: KEY });
    },
    onError: (cause) => {
      // ⚠️  ٤٠٩ = آخر بوابة مفعّلة. الرسالة من الخادم محدّدة ومفيدة.
      notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
    },
  });

  if (providers.isPending) return <Spinner />;

  const activeCount = providers.data?.filter((provider) => provider.is_active).length ?? 0;

  return (
    <>
      <PageHeader title={t('nav.payments')} description={t('admin.gatewaysHint')} />

      {activeCount === 0 ? (
        <Alert tone="danger">{t('admin.noActiveGateway')}</Alert>
      ) : null}

      <div className="gateways">
        {providers.data?.map((provider) => (
          <GatewayCard
            key={provider.id}
            provider={provider}
            reason={reasons[provider.id] ?? ''}
            onReasonChange={(value) => {
              setReasons((current) => ({ ...current, [provider.id]: value }));
            }}
            onToggle={() => {
              toggle.mutate({
                id: provider.id,
                isActive: !provider.is_active,
                reason: reasons[provider.id] ?? '',
              });
            }}
            pending={toggle.isPending}
            localized={localized}
          />
        ))}
      </div>
    </>
  );
}

function GatewayCard({
  provider,
  reason,
  onReasonChange,
  onToggle,
  pending,
  localized,
}: {
  provider: PaymentProvider;
  reason: string;
  onReasonChange: (value: string) => void;
  onToggle: () => void;
  pending: boolean;
  localized: (source: object, field: string) => string;
}) {
  const { t } = useTranslation();

  // ⚠️  البوابة الخارجية بلا مفاتيح لا تُفعَّل — الخادم يرفض،
  //     وإخفاء الزر يمنع محاولة محكوم عليها بالفشل.
  const blocked = !provider.is_active && !provider.is_configured && provider.credential_keys.length === 0;

  return (
    <article className={`gateway surface ${provider.is_active ? 'is-active' : ''}`}>
      <header className="gateway__head">
        <div>
          <strong className="gateway__name">{localized(provider, 'name')}</strong>
          <code className="gateway__code muted">{provider.code}</code>
        </div>

        {provider.is_active ? (
          <Badge tone="success">{t('admin.enabled')}</Badge>
        ) : (
          <Badge tone="neutral">{t('admin.disabled')}</Badge>
        )}
      </header>

      <dl className="gateway__facts">
        <div>
          <dt>{t('admin.adapter')}</dt>
          <dd>
            <code style={{ direction: 'ltr' }}>{provider.adapter_key}</code>
            {!provider.adapter_exists ? (
              <Badge tone="danger">{t('admin.adapterMissing')}</Badge>
            ) : null}
          </dd>
        </div>

        <div>
          <dt>{t('admin.mode')}</dt>
          <dd>{provider.is_sandbox ? t('admin.sandbox') : t('admin.production')}</dd>
        </div>

        <div>
          <dt>{t('admin.credentials')}</dt>
          <dd>
            {provider.credential_keys.length > 0
              ? provider.credential_keys.join(' · ')
              : t('admin.noCredentials')}
          </dd>
        </div>

        <div>
          <dt>{t('admin.methods')}</dt>
          <dd>{provider.supported_methods.join(' · ')}</dd>
        </div>
      </dl>

      {blocked ? (
        <Alert tone="warning">{t('admin.needsCredentials')}</Alert>
      ) : (
        <div className="gateway__action">
          <input
            className="gateway__reason"
            value={reason}
            placeholder={t('admin.toggleReason')}
            aria-label={t('admin.toggleReason')}
            onChange={(event) => {
              onReasonChange(event.target.value);
            }}
          />

          <Button
            variant={provider.is_active ? 'secondary' : 'primary'}
            disabled={pending || !provider.adapter_exists}
            onClick={onToggle}
          >
            {provider.is_active ? t('admin.disable') : t('admin.enable')}
          </Button>
        </div>
      )}
    </article>
  );
}
