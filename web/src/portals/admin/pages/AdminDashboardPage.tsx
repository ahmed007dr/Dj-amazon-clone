import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { listAccounts } from '@/features/administration/api';
import { getLivePulse } from '@/features/analytics/api';
import { listAlerts } from '@/features/inventory/api';
import { listAdminOrders } from '@/features/orders/adminApi';
import { listProviders } from '@/features/payments/adminApi';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { StatCard } from '@/shared/ui/StatCard';

import './AdminDashboardPage.css';

/**
 * The dashboard.
 *
 * ⚠️  **Figures that call for an action, not figures for display.**
 *
 *     "Total products 23" changes nothing; whereas "7 orders awaiting
 *     confirmation" and "3 stock alerts" are both work that starts now. Which
 *     is why every card here is a link to where the action happens, not a
 *     silent number.
 */
export function AdminDashboardPage() {
  const { t } = useTranslation();

  const pending = useQuery({
    queryKey: ['admin', 'dash', 'pending'],
    queryFn: () => listAdminOrders({ status: 'PENDING', page: 1 }),
    staleTime: 30 * 1000,
  });

  const processing = useQuery({
    queryKey: ['admin', 'dash', 'processing'],
    queryFn: () => listAdminOrders({ status: 'PROCESSING', page: 1 }),
    staleTime: 30 * 1000,
  });

  const alerts = useQuery({
    queryKey: ['admin', 'dash', 'alerts'],
    queryFn: () => listAlerts({ page: 1 }),
    staleTime: 30 * 1000,
  });

  /**
   * ⚠️  `analytics/live`, not `online-now`.
   *
   *     The latter serialises every connected user with their profile and their
   *     recent actions — heavy work repeated every thirty seconds in every open
   *     panel for the sake of one number. The former is three counts alone, so
   *     monitoring the load does not become the load.
   */
  const live = useQuery({
    queryKey: ['admin', 'live-pulse'],
    queryFn: getLivePulse,
    refetchInterval: 30 * 1000,
  });

  const pendingVerification = useQuery({
    queryKey: ['admin', 'dash', 'verification'],
    queryFn: () => listAccounts({ verification_status: 'PENDING', page: 1 }),
    staleTime: 60 * 1000,
  });

  const providers = useQuery({
    queryKey: ['admin', 'payment-providers'],
    queryFn: listProviders,
    staleTime: 5 * 60 * 1000,
  });

  const activeGateways = providers.data?.filter((provider) => provider.is_active).length ?? 0;

  return (
    <>
      <PageHeader title={t('nav.dashboard')} description={t('admin.dashboardHint')} />

      {/* ⚠️  A store with no enabled gateway accepts no orders — and the discovery
          comes through a customer complaint. This warning precedes everything. */}
      {providers.data && activeGateways === 0 ? (
        <Alert tone="danger">{t('admin.noActiveGateway')}</Alert>
      ) : null}

      <div className="dashboard">
        <Link to="/admin/orders" className="dashboard__link">
          <StatCard
            label={t('admin.pendingOrders')}
            value={pending.data?.count ?? '—'}
            hint={t('admin.pendingOrdersHint')}
            tone={pending.data && pending.data.count > 0 ? 'warning' : 'neutral'}
            icon="▤"
          />
        </Link>

        <Link to="/admin/orders" className="dashboard__link">
          <StatCard
            label={t('admin.processingOrders')}
            value={processing.data?.count ?? '—'}
            hint={t('admin.processingOrdersHint')}
            icon="⇄"
          />
        </Link>

        <Link to="/admin/inventory" className="dashboard__link">
          <StatCard
            label={t('admin.stockAlerts')}
            value={alerts.data?.count ?? '—'}
            hint={t('admin.stockAlertsHint')}
            tone={alerts.data && alerts.data.count > 0 ? 'danger' : 'success'}
            icon="⚠"
          />
        </Link>

        <Link to="/admin/users" className="dashboard__link">
          <StatCard
            label={t('admin.awaitingVerification')}
            value={pendingVerification.data?.count ?? '—'}
            hint={t('admin.awaitingVerificationHint')}
            tone={
              pendingVerification.data && pendingVerification.data.count > 0
                ? 'warning'
                : 'neutral'
            }
            icon="⚿"
          />
        </Link>

        {/* ⚠️  Two cards, not one.
            A registered user has a name and a profile that opens with a click;
            an anonymous one is a count with no identity. Merging them into "15
            online" produces a figure matched by only three rows in the users
            table — a visible contradiction that costs the dashboard its credibility. */}
        <Link to="/admin/users" className="dashboard__link">
          <StatCard
            label={t('admin.onlineNow')}
            value={live.data?.users_online ?? '—'}
            hint={t('admin.onlineHint')}
            tone="success"
            icon="●"
          />
        </Link>

        <Link to="/admin/traffic" className="dashboard__link">
          <StatCard
            label={t('traffic.guestsOnline')}
            value={live.data?.guests_online ?? '—'}
            hint={t('traffic.guestsOnlineHint')}
            tone="neutral"
            icon="◍"
          />
        </Link>

        <Link to="/admin/payments" className="dashboard__link">
          <StatCard
            label={t('admin.activeGateways')}
            value={activeGateways}
            hint={t('admin.activeGatewaysHint')}
            tone={activeGateways === 0 ? 'danger' : 'neutral'}
            icon="⛁"
          />
        </Link>
      </div>
    </>
  );
}
