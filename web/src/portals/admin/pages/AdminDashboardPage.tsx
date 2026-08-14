import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { getOnlineNow, listAccounts } from '@/features/administration/api';
import { listAlerts } from '@/features/inventory/api';
import { listAdminOrders } from '@/features/orders/adminApi';
import { listProviders } from '@/features/payments/adminApi';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { StatCard } from '@/shared/ui/StatCard';

import './AdminDashboardPage.css';

/**
 * لوحة المعلومات.
 *
 * ⚠️  **أرقام تستدعي تصرّفًا لا أرقام للعرض.**
 *
 *     «إجمالي المنتجات ٢٣» لا يُغيّر شيئًا؛ أما «٧ طلبات تنتظر
 *     التأكيد» و«٣ تنبيهات مخزون» فكلاهما عمل يبدأ الآن. ولذلك كل
 *     بطاقة هنا رابط إلى مكان الفعل لا رقم صامت.
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

  const online = useQuery({
    queryKey: ['admin', 'online-now'],
    queryFn: getOnlineNow,
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

      {/* ⚠️  متجر بلا بوابة مفعّلة لا يستقبل طلبات — والاكتشاف
          يكون بشكوى عميل. هذا التحذير يسبق كل شيء. */}
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

        <Link to="/admin/users" className="dashboard__link">
          <StatCard
            label={t('admin.onlineNow')}
            value={online.data?.length ?? '—'}
            hint={t('admin.onlineHint')}
            tone="success"
            icon="●"
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
