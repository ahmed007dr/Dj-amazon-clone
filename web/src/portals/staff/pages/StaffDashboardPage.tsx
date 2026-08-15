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
 * لوحة أداء المندوب.
 *
 * ⚠️  **تُركَّب من ثلاث نقاط لا واحدة.**
 *
 *     `employees` تحت `targets` و`commissions` في ترتيب الطبقات
 *     على الخادم، فلا نقطة واحدة تجمعها. والتركيب هنا ثلاثة
 *     استعلامات متوازية صغيرة — أرخص من كسر حدود النطاقات.
 *
 * ⚠️  و**الهدف أعلى الشاشة قبل الأرقام**.
 *
 *     المندوب يفتحها ليعرف موقفه من هدفه؛ ودفنه تحت ستّ بطاقات
 *     إحصائية يجعله يبحث عمّا جاء من أجله.
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

      {/* ⚠️  «لا هدف» رسالة صريحة لا شاشة فارغة: غيابه أول الشهر
          حالة عادية تنتظر الإدارة، لا عطل ولا أداء سيئ. */}
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
        {/* ⚠️  المرتجعات تُعرَض دائمًا ولو صفرًا: إخفاؤها عند الصفر
            يجعل ظهورها لاحقًا يبدو حقلًا جديدًا لا رقمًا تغيّر. */}
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
