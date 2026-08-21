import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  listProviders,
  toggleProvider,
  useDeleteProvider,
  useReorderProviders,
  type PaymentProvider,
} from '@/features/payments/adminApi';
import { ProviderForm } from '@/portals/admin/components/ProviderForm';
import { Drawer } from '@/shared/ui/Drawer';
import { isApiError } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { TransactionsPanel } from '@/portals/admin/components/TransactionsPanel';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './AdminPaymentsPage.css';

const KEY = ['admin', 'payment-providers'] as const;

/**
 * Payment gateways.
 *
 * ⚠️  Enabling and disabling **take effect immediately with no redeployment** —
 *     and that is the heart of ADR-15: the gateways are data and the adapters are code.
 */
export function AdminPaymentsPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [reasons, setReasons] = useState<Record<string, string>>({});

  const [tab, setTab] = useState<'providers' | 'transactions'>('providers');
  const [editing, setEditing] = useState<PaymentProvider | null>(null);
  const [creating, setCreating] = useState(false);

  const removeProvider = useDeleteProvider();
  const reorder = useReorderProviders();

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
      // ⚠️  409 = the last enabled gateway. The server's message is specific and useful.
      notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
    },
  });

  if (providers.isPending) return <Spinner />;

  const activeCount = providers.data?.filter((provider) => provider.is_active).length ?? 0;

  return (
    <>
      <PageHeader
        title={t('nav.payments')}
        description={t('admin.gatewaysHint')}
        actions={
          tab === 'providers' ? (
            <Button onClick={() => setCreating(true)}>{t('admin.newGateway')}</Button>
          ) : null
        }
      />

      <StatusTabs
        options={[
          { value: 'providers', label: t('payments.tabProviders') },
          { value: 'transactions', label: t('payments.tabTransactions') },
        ]}
        value={tab}
        onChange={(next) => setTab(next as 'providers' | 'transactions')}
      />

      {tab === 'transactions' ? <TransactionsPanel /> : null}

      {tab !== 'providers' ? null : (
      <>
      {activeCount === 0 ? (
        <Alert tone="danger">{t('admin.noActiveGateway')}</Alert>
      ) : null}

      <div className="gateways">
        {providers.data?.map((provider, index) => (
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
            onEdit={() => setEditing(provider)}
            onDelete={() =>
              removeProvider.mutate(provider.id, {
                onSuccess: () => notify(t('admin.gatewayDeleted'), 'success'),
                onError: (cause) =>
                  notify(
                    isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                    'danger',
                  ),
              })
            }
            {...(index > 0
              ? {
                  onMoveUp: () => {
                    // ⚠️  The ordering is sent **in full**, not as a single position:
                    //     the server renumbers the priorities from the list, and sending
                    //     a partial swap leaves gaps that accumulate until two gateways tie.
                    const order = (providers.data ?? []).map((row) => row.id);
                    const above = order[index - 1];
                    const current = order[index];
                    if (above === undefined || current === undefined) return;
                    order[index - 1] = current;
                    order[index] = above;
                    reorder.mutate(order, {
                      onError: (cause) =>
                        notify(
                          isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                          'danger',
                        ),
                    });
                  },
                }
              : {})}
          />
        ))}
      </div>
      </>
      )}

      <Drawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        title={editing ? localized(editing, 'name') : t('admin.newGateway')}
      >
        {creating || editing ? (
          <ProviderForm
            key={editing?.id ?? 'new'}
            {...(editing ? { provider: editing } : {})}
            onDone={() => {
              setCreating(false);
              setEditing(null);
            }}
          />
        ) : null}
      </Drawer>
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
  onEdit,
  onDelete,
  onMoveUp,
}: {
  provider: PaymentProvider;
  reason: string;
  onReasonChange: (value: string) => void;
  onToggle: () => void;
  pending: boolean;
  localized: (source: object, field: string) => string;
  onEdit: () => void;
  onDelete: () => void;
  /** Absent on the first — there is nothing above it to move up to */
  onMoveUp?: () => void;
}) {
  const { t } = useTranslation();

  // ⚠️  An external gateway with no keys is not enabled — the server refuses,
  //     and hiding the button prevents an attempt doomed to fail.
  const blocked = !provider.is_active && !provider.is_configured && provider.credential_keys.length === 0;

  return (
    <article className={`gateway surface ${provider.is_active ? 'is-active' : ''}`}>
      <header className="gateway__head">
        <div>
          <strong className="gateway__name">{localized(provider, 'name')}</strong>
          <code className="gateway__code muted">{provider.code}</code>
        </div>

        <div className="gateway__badges">
          {provider.is_active ? (
            <Badge tone="success">{t('admin.enabled')}</Badge>
          ) : (
            <Badge tone="neutral">{t('admin.disabled')}</Badge>
          )}

          {/* ⚠️  The priority is visible: it is what determines which gateway is tried
              first when more than one is suitable — and the decision steers the money. */}
          <span className="gateway__priority muted">
            {t('admin.priority')}: {provider.priority}
          </span>
        </div>
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

      <footer className="gateway__manage">
        {onMoveUp ? (
          <Button size="sm" variant="ghost" onClick={onMoveUp}>
            ↑ {t('admin.raisePriority')}
          </Button>
        ) : null}

        <Button size="sm" variant="ghost" onClick={onEdit}>
          {t('common.edit')}
        </Button>

        {/* ⚠️  Deletion appears for disabled ones alone: the server refuses to delete a
            gateway with transactions, and an enabled one is disabled first — and
            a button refused when pressed is a bad experience. */}
        {!provider.is_active ? (
          <Button size="sm" variant="ghost" onClick={onDelete}>
            {t('common.delete')}
          </Button>
        ) : null}
      </footer>
    </article>
  );
}
