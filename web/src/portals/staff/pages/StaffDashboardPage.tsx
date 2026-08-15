import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDashboard } from '@/features/employees/api';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Spinner } from '@/shared/ui/Spinner';
import { StatCard } from '@/shared/ui/StatCard';

import { MonthlyHistory } from '../components/MonthlyHistory';

import './StaffDashboardPage.css';

/**
 * لوحة أداء المندوب.
 *
 * ⚠️  **الهدف والعمولة يُعلَن غيابهما — لا يُعرَضان صفرًا.**
 *
 *     المندوب يفتح هذه الشاشة أول كل صباح ليقيس نفسه. «تحقيقك
 *     ٠٪» يُقرأ أداءً سيئًا لا نظامًا لم يُضبَط بعد — وهو فرق بين
 *     موظف محبَط وموظف ينتظر. الخادم يرسل `null` ومعه سبب،
 *     والشاشة تقول السبب صراحةً.
 */
export function StaffDashboardPage() {
  const { t } = useTranslation();
  const [period] = useState<{ start?: string; end?: string }>({});

  const query = useDashboard(period);

  if (query.isPending) return <Spinner />;
  if (!query.data) return null;

  const data = query.data;

  return (
    <>
      <PageHeader title={t('staff.dashboard')} description={data.full_name} />

      {data.target === null ? (
        <Alert tone="info">{t('staff.targetsPending')}</Alert>
      ) : null}

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

      <MonthlyHistory rows={data.history} />
    </>
  );
}
