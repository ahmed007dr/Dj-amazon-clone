import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCustomersReport,
  useInventoryReport,
  useOverview,
  usePerformanceReport,
  useSalesReport,
} from '@/features/reporting/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Spinner } from '@/shared/ui/Spinner';
import { StatCard } from '@/shared/ui/StatCard';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate } from '@/shared/utils/format';

import { PeriodPicker } from '../components/PeriodPicker';
import { RankedList } from '../components/RankedList';
import { TrendBars } from '../components/TrendBars';

import './AdminReportsPage.css';

type Tab = 'overview' | 'sales' | 'inventory' | 'customers' | 'performance';

const TABS: Tab[] = ['overview', 'sales', 'inventory', 'customers', 'performance'];

/**
 * التقارير.
 *
 * ⚠️  **كل رقم هنا مشتق من مصدره لحظة الطلب.**
 *
 *     لا جدول تقارير مخزَّن: نسخة مُجمَّعة تنشئ رقمًا ثالثًا يجب
 *     أن يوازي مصدرين، وأول انحراف لا يملك أحد حسمه.
 *
 * ⚠️  والتبويبات **تجلب عند فتحها فقط**.
 *
 *     جلب الخمسة معًا يعني خمسة استعلامات تجميع ثقيلة عند كل فتح
 *     للشاشة — وأربعة منها لا تُقرأ.
 */
export function AdminReportsPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const [tab, setTab] = useState<Tab>('overview');
  const [period, setPeriod] = useState<{ start?: string; end?: string }>({});

  const overview = useOverview(period);
  // ⚠️  `enabled` عبر مفتاح ثابت: الاستعلام لا يُطلَق قبل فتح تبويبه.
  const sales = useSalesReport(tab === 'sales' ? period : { start: '', end: '' });
  const inventory = useInventoryReport(90);
  const customers = useCustomersReport(period);
  const performance = usePerformanceReport(period);

  if (isApiError(overview.error) && overview.error.status === 403) {
    return (
      <>
        <PageHeader title={t('reports.title')} />
        <StateMessage icon="🔒" title={t('reports.noAccess')} body={t('reports.noAccessBody')} />
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('reports.title')} />

      <PeriodPicker value={period} onChange={setPeriod} />

      <div className="reports-tabs" role="tablist">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? 'is-active' : ''}
            onClick={() => setTab(name)}
          >
            {t(`reports.tab.${name}`)}
          </button>
        ))}
      </div>

      {tab === 'overview' ? (
        overview.isPending ? (
          <Spinner />
        ) : overview.data ? (
          <>
            {/* ⚠️  التحذير فوق الأرقام لا تحتها: قراءة الرقم قبل
                التحذير تعني أن القرار اتُّخذ. */}
            {!overview.data.profit_is_reliable ? (
              <Alert tone="warning">{t('reports.profitUnreliable')}</Alert>
            ) : null}

            <div className="reports-grid">
              <StatCard label={t('reports.netSales')} value={overview.data.net_sales} />
              <StatCard label={t('reports.grossProfit')} value={overview.data.gross_profit} />
              <StatCard
                label={t('reports.margin')}
                value={`${overview.data.gross_margin}%`}
              />
              <StatCard label={t('reports.netProfit')} value={overview.data.net_profit} />
              <StatCard
                label={t('reports.orders')}
                value={String(overview.data.orders_count)}
              />
              <StatCard label={t('reports.avgOrder')} value={overview.data.average_order} />
            </div>

            <h2 className="reports-heading">{t('reports.inventoryNow')}</h2>
            <div className="reports-grid">
              {/* ⚠️  «بالتكلفة» في التسمية نفسها — التقييم بسعر
                  البيع خطأ محاسبي، والتسمية تمنع قراءته خطأً. */}
              <StatCard
                label={t('reports.stockValue')}
                value={overview.data.inventory.stock_value_at_cost}
              />
              <StatCard
                label={t('reports.belowReorder')}
                value={String(overview.data.inventory.products_below_reorder)}
                tone={overview.data.inventory.products_below_reorder > 0 ? 'warning' : 'neutral'}
              />
              <StatCard
                label={t('reports.outOfStock')}
                value={String(overview.data.inventory.products_out_of_stock)}
                tone={overview.data.inventory.products_out_of_stock > 0 ? 'danger' : 'neutral'}
              />
            </div>
          </>
        ) : null
      ) : null}

      {tab === 'sales' ? (
        sales.isPending ? (
          <Spinner />
        ) : sales.data ? (
          <>
            <TrendBars
              rows={sales.data.by_day.map((row) => ({
                label: row.day.slice(5),
                value: Number(row.total),
              }))}
            />

            <div className="reports-columns">
              <RankedList
                title={t('reports.topProducts')}
                rows={sales.data.top_products.map((row) => ({
                  key: row.product,
                  label: localized(row, 'name'),
                  meta: `${row.quantity} ${t('reports.units')}`,
                  value: row.revenue,
                }))}
              />
              <RankedList
                title={t('reports.byCategory')}
                rows={sales.data.by_category.map((row) => ({
                  key: row.slug,
                  label: localized(row, 'name'),
                  value: row.revenue,
                }))}
              />
              <RankedList
                title={t('reports.byChannel')}
                rows={sales.data.by_channel.map((row) => ({
                  key: row.channel,
                  label: t(`reports.channel.${row.channel}`, { defaultValue: row.channel }),
                  meta: `${row.orders} ${t('reports.orders')}`,
                  value: row.total,
                }))}
              />
            </div>
          </>
        ) : null
      ) : null}

      {tab === 'inventory' ? (
        inventory.isPending ? (
          <Spinner />
        ) : inventory.data ? (
          <>
            <div className="reports-grid">
              <StatCard
                label={t('reports.stockValue')}
                value={inventory.data.summary.stock_value_at_cost}
              />
              <StatCard
                label={t('reports.batches')}
                value={String(inventory.data.summary.batches)}
              />
            </div>

            <h2 className="reports-heading">{t('reports.expiring')}</h2>
            {inventory.data.expiring.length === 0 ? (
              <StateMessage icon="✓" title={t('reports.nothingExpiring')} />
            ) : (
              <ul className="reports-expiry">
                {inventory.data.expiring.map((row) => (
                  <li key={row.batch} className={row.is_expired ? 'is-expired' : ''}>
                    <span className="truncate">{localized(row, 'name')}</span>
                    <code>{row.batch}</code>
                    <span dir="ltr">{formatDate(row.expires_at, i18n.language)}</span>
                    {/* ⚠️  المنتهي يُقال صراحةً لا يُترك رقمًا سالبًا
                        يُقرأ «قريب». */}
                    <strong className={row.is_expired ? 'is-expired-flag' : ''}>
                      {row.is_expired
                        ? t('reports.expired')
                        : t('reports.daysLeft', { count: row.days_left })}
                    </strong>
                    <span dir="ltr">{row.value_at_cost}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null
      ) : null}

      {tab === 'customers' ? (
        customers.isPending ? (
          <Spinner />
        ) : customers.data ? (
          <>
            <div className="reports-grid">
              <StatCard
                label={t('reports.newCustomers')}
                value={String(customers.data.new_customers)}
              />
              <StatCard
                label={t('reports.returning')}
                value={String(customers.data.returning_customers)}
              />
              <StatCard
                label={t('reports.active')}
                value={String(customers.data.active_customers)}
              />
            </div>

            <div className="reports-columns">
              <RankedList
                title={t('reports.topCustomers')}
                rows={customers.data.top_customers.map((row) => ({
                  key: row.customer,
                  label: row.name,
                  meta: `${row.orders} ${t('reports.orders')}`,
                  value: row.total,
                }))}
              />
              <RankedList
                title={t('reports.bySegment')}
                rows={customers.data.by_segment.map((row) => ({
                  key: row.segment,
                  label: row.segment,
                  meta: `${row.customers}`,
                  value: row.total,
                }))}
              />
            </div>
          </>
        ) : null
      ) : null}

      {tab === 'performance' ? (
        performance.isPending ? (
          <Spinner />
        ) : performance.data ? (
          <div className="reports-columns">
            <RankedList
              title={t('reports.employees')}
              rows={performance.data.employees.map((row) => ({
                key: row.employee,
                label: row.name,
                meta: `${row.role} · ${row.orders}`,
                value: row.total,
              }))}
            />
            <RankedList
              title={t('reports.suppliers')}
              rows={performance.data.suppliers.map((row) => ({
                key: row.supplier,
                label: localized(row, 'name'),
                meta: `${row.orders} ${t('reports.purchaseOrders')}`,
                value: row.total,
              }))}
            />
          </div>
        ) : null
      ) : null}
    </>
  );
}
