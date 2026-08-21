import { useTranslation } from 'react-i18next';

import { useDashboard } from '@/features/employees/api';
import { useMyCommissions, useMyTarget } from '@/features/targets/api';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Spinner } from '@/shared/ui/Spinner';
import { StatCard } from '@/shared/ui/StatCard';

import { CommissionCard } from '../components/CommissionCard';
import { MonthlyHistory } from '../components/MonthlyHistory';
import { TargetGauge } from '../components/TargetGauge';

import './StaffDashboardPage.css';

/**
 * The rep's performance dashboard.
 *
 * ⚠️  **Assembled from three endpoints, not one.**
 *
 *     `employees` sits below `targets` and `commissions` in the server's layer
 *     ordering, so no single endpoint gathers them. Assembling here is three
 *     small parallel queries — cheaper than breaking the domain boundaries.
 *
 * ⚠️  And **the target sits at the top of the screen, before the figures**.
 *
 *     The rep opens it to learn where they stand against their target; burying
 *     it under six statistics cards makes them search for what they came for.
 */
export function StaffDashboardPage() {
  const { t } = useTranslation();

  const performance = useDashboard({});
  const target = useMyTarget();
  const commissions = useMyCommissions();

  if (performance.isPending) return <Spinner />;
  if (!performance.data) return null;

  const data = performance.data;
  const records = commissions.data?.results ?? [];

  return (
    <>
      <PageHeader title={t('staff.dashboard')} description={data.full_name} />

      {/* ⚠️  "No target" is an explicit message rather than an empty screen: its
          absence at the start of the month is a normal state awaiting
          management — neither a fault nor poor performance. */}
      {target.isPending ? (
        <Spinner />
      ) : target.data ? (
        <TargetGauge data={target.data} />
      ) : (
        <Alert tone="info">{t('targets.noTarget')}</Alert>
      )}

      <div className="staff-stats">
        <StatCard label={t('staff.netSales')} value={data.net_sales} />
        <StatCard label={t('staff.ordersCount')} value={String(data.orders_count)} />
        <StatCard label={t('staff.averageOrder')} value={data.average_order} />
        <StatCard label={t('staff.customersCount')} value={String(data.customers_count)} />
        <StatCard label={t('staff.newCustomers')} value={String(data.new_customers)} />
        {/* ⚠️  Returns are always displayed, even at zero: hiding them at zero
            makes their later appearance look like a new field rather than a figure that changed. */}
        <StatCard label={t('staff.returns')} value={data.returns_total} />
      </div>

      {records.length > 0 ? (
        <section className="staff-commissions">
          <h2>{t('targets.myCommissions')}</h2>
          <div className="staff-commissions__grid">
            {records.map((record) => (
              <CommissionCard key={record.id} record={record} />
            ))}
          </div>
        </section>
      ) : null}

      <MonthlyHistory rows={data.history} />
    </>
  );
}
