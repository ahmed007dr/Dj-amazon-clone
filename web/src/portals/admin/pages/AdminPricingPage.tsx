import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCoupons,
  useDeleteCoupon,
  useDeleteOverride,
  useDeletePriceList,
  useDeletePriceRule,
  usePriceLists,
  usePriceOverrides,
  usePriceRules,
  type Coupon,
  type PriceList,
  type PriceOverride,
  type PriceRule,
} from '@/features/pricing/api';
import { downloadExport } from '@/features/exports/adminApi';
import { CouponBulkForm } from '@/portals/admin/components/CouponBulkForm';
import { CouponForm } from '@/portals/admin/components/CouponForm';
import {
  CouponInsightsDrawer,
  type InsightsTarget,
} from '@/portals/admin/components/CouponInsightsDrawer';
import { CouponRedemptionsDrawer } from '@/portals/admin/components/CouponRedemptionsDrawer';
import { CouponReport } from '@/portals/admin/components/CouponReport';
import { scopeLabel, scopeTooltip } from '@/portals/admin/components/couponScope';
import { CouponPeriodFilter, CouponStatsBar } from '@/portals/admin/components/CouponStatsBar';
import {
  ALL_TIME,
  periodParams,
  type PeriodState,
} from '@/portals/admin/components/couponPeriod';
import { PriceListForm } from '@/portals/admin/components/PriceListForm';
import { PriceRuleForm } from '@/portals/admin/components/PriceRuleForm';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useTabParam } from '@/shared/hooks/useTabParam';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { ActionMenu } from '@/shared/ui/ActionMenu';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';
import { formatDate, formatMoney } from '@/shared/utils/format';

import './AdminPricingPage.css';

type Tab = 'lists' | 'overrides' | 'coupons';

/** The coupons tab's two views: the table, and the customer/discount report (`?view=`). */
const COUPON_VIEWS = ['list', 'report'] as const;

/**
 * Pricing and offers.
 *
 * ⚠️  **Separate lists, not discount percentages** (business rule 9): a
 *     student's price is a price in its own right, not derived from the retail
 *     price. Which is why this screen has no "student discount percentage"
 *     field — but a complete price list.
 *
 * ⚠️  And **a promotional discount is not a coupon**: the first appears in the
 *     catalogue with no code, and the second is entered by the customer. Mixing
 *     them into one tab makes the admin create both for the same campaign, so
 *     the discount is applied twice.
 */
export function AdminPricingPage() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('lists');
  const [selectedList, setSelectedList] = useState<string>('');
  const [search, setSearch] = useState('');
  const [couponStatus, setCouponStatus] = useState('');
  const [couponScope, setCouponScope] = useState('');
  const [couponGuests, setCouponGuests] = useState('');
  const [couponView, setCouponView] = useTabParam(COUPON_VIEWS, 'list', 'view');
  const [page, setPage] = useState(1);

  const [editingList, setEditingList] = useState<PriceList | null>(null);
  const [editingRule, setEditingRule] = useState<PriceRule | null>(null);
  const [editingCoupon, setEditingCoupon] = useState<Coupon | null>(null);
  const [usageOf, setUsageOf] = useState<Coupon | null>(null);
  const [creating, setCreating] = useState(false);

  // Coupon analytics: one period for the cards, the table, the drawer and the export
  const [period, setPeriod] = useState<PeriodState>(ALL_TIME);
  const [insightsOf, setInsightsOf] = useState<InsightsTarget | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const periodQuery = periodParams(period);

  const debouncedSearch = useDebounced(search);

  const lists = usePriceLists();
  const rules = usePriceRules({
    ...(selectedList ? { price_list: selectedList } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    page,
  });
  const overrides = usePriceOverrides({ page }, tab === 'overrides');
  const coupons = useCoupons(
    {
      ...(debouncedSearch ? { search: debouncedSearch } : {}),
      ...(couponStatus ? { status: couponStatus } : {}),
      ...(couponScope ? { scope: couponScope } : {}),
      ...(couponGuests ? { guests: couponGuests } : {}),
      ...periodQuery,
      page,
    },
    tab === 'coupons' && couponView === 'list',
  );

  const removeList = useDeletePriceList();
  const removeRule = useDeletePriceRule();
  const removeOverride = useDeleteOverride();
  const removeCoupon = useDeleteCoupon();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  // ⚠️  Through the export system's own download flow (bearer token, audit entry,
  //     row ceiling) with the same period and search the screen is showing — a file
  //     that disagrees with the table in front of the owner is worse than no file.
  const exportCoupons = async () => {
    setExporting(true);
    try {
      await downloadExport('coupons', {
        start: periodQuery.date_from ?? '',
        end: periodQuery.date_to ?? '',
        search: debouncedSearch,
      });
      notify(t('pricing.insights.exported'), 'success');
    } catch (error) {
      fail(error);
    } finally {
      setExporting(false);
    }
  };

  const closeDrawer = () => {
    setCreating(false);
    setEditingList(null);
    setEditingRule(null);
    setEditingCoupon(null);
  };

  // ── Columns ─────────────────────────────────────────────

  const listColumns: Column<PriceList>[] = [
    {
      key: 'name',
      header: t('pricing.list'),
      render: (row) => (
        <span>
          <code style={{ direction: 'ltr' }}>{row.code}</code> — {row.name_ar}
          {row.is_default ? <Badge tone="info">{t('pricing.default')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'kind',
      header: t('pricing.kind'),
      secondary: true,
      render: (row) => t(`priceListKind.${row.kind}`),
    },
    {
      key: 'rules',
      header: t('pricing.rules'),
      align: 'end',
      // ⚠️  Zero is highlighted rather than buried: an enabled list with no rules
      //     means its customers see the retail price while believing they are on wholesale.
      render: (row) =>
        row.rule_count === 0 ? (
          <Badge tone="warning">{t('pricing.noRules')}</Badge>
        ) : (
          row.rule_count
        ),
    },
    {
      key: 'validity',
      header: t('admin.validity'),
      secondary: true,
      render: (row) =>
        row.is_currently_valid ? (
          <Badge tone="success">{t('admin.valid')}</Badge>
        ) : (
          <Badge tone="neutral">{t('admin.notValid')}</Badge>
        ),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      // ⚠️  One dropdown per row. The default list gets no "delete" item at all (hidden, not
      //     merely disabled), exactly as it got no delete button before.
      render: (row) => (
        <ActionMenu
          menuLabel={`${t('admin.actions')} · ${row.name_ar}`}
          items={[
            {
              key: 'rules',
              label: t('pricing.openRules'),
              onSelect: () => setSelectedList(row.id),
            },
            {
              key: 'edit',
              label: t('common.edit'),
              onSelect: () => setEditingList(row),
            },
            {
              key: 'delete',
              label: t('common.delete'),
              tone: 'danger',
              hidden: row.is_default,
              disabled: removeList.isPending,
              onSelect: () =>
                removeList.mutate(row.id, {
                  onSuccess: () => notify(t('pricing.deleted'), 'success'),
                  onError: fail,
                }),
            },
          ]}
        />
      ),
    },
  ];

  const ruleColumns: Column<PriceRule>[] = [
    {
      key: 'product',
      header: t('catalog.product'),
      render: (row) => (
        <span>
          <code style={{ direction: 'ltr' }}>{row.product_sku}</code> — {row.product_name}
        </span>
      ),
    },
    {
      key: 'tier',
      header: t('pricing.minQuantity'),
      align: 'end',
      // ⚠️  "From 10 upwards", not "10": the number alone reads as a fixed quantity.
      render: (row) => t('pricing.fromQuantity', { count: row.min_quantity }),
    },
    {
      key: 'price',
      header: t('pricing.unitPrice'),
      align: 'end',
      render: (row) => formatMoney(row.unit_price, i18n.language),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <ActionMenu
          menuLabel={`${t('admin.actions')} · ${row.product_name}`}
          items={[
            {
              key: 'edit',
              label: t('common.edit'),
              onSelect: () => setEditingRule(row),
            },
            {
              key: 'delete',
              label: t('common.delete'),
              tone: 'danger',
              disabled: removeRule.isPending,
              onSelect: () =>
                removeRule.mutate(row.id, {
                  onSuccess: () => notify(t('pricing.deleted'), 'success'),
                  onError: fail,
                }),
            },
          ]}
        />
      ),
    },
  ];

  const overrideColumns: Column<PriceOverride>[] = [
    {
      key: 'product',
      header: t('catalog.product'),
      render: (row) => (
        <span>
          <code style={{ direction: 'ltr' }}>{row.product_sku}</code> — {row.product_name}
        </span>
      ),
    },
    {
      key: 'discount',
      header: t('pricing.discount'),
      align: 'end',
      render: (row) =>
        row.discount_kind === 'PERCENTAGE'
          ? `${row.discount_value}%`
          : formatMoney(row.discount_value, i18n.language),
    },
    {
      key: 'window',
      header: t('pricing.window'),
      secondary: true,
      render: (row) =>
        `${formatDate(row.starts_at, i18n.language)} — ${
          row.ends_at ? formatDate(row.ends_at, i18n.language) : t('pricing.noEnd')
        }`,
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) =>
        row.is_running ? (
          <Badge tone="success">{t('pricing.running')}</Badge>
        ) : (
          <Badge tone="neutral">{t('pricing.notRunning')}</Badge>
        ),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      // A single action, kept in a menu like every other row here: the same trigger in the
      // same place on every tab, and "delete" is never one stray click from the status badge.
      render: (row) => (
        <ActionMenu
          menuLabel={`${t('admin.actions')} · ${row.product_name}`}
          items={[
            {
              key: 'delete',
              label: t('common.delete'),
              tone: 'danger',
              disabled: removeOverride.isPending,
              onSelect: () =>
                removeOverride.mutate(row.id, {
                  onSuccess: () => notify(t('pricing.deleted'), 'success'),
                  onError: fail,
                }),
            },
          ]}
        />
      ),
    },
  ];

  const couponColumns: Column<Coupon>[] = [
    {
      key: 'code',
      header: t('pricing.couponCode'),
      render: (row) => (
        <span>
          {/* ⚠️  The code opens the insights: it is the cell the eye lands on, and a
              row-wide click would fight the actions menu beside it. */}
          <button
            type="button"
            className="coupon-code-link"
            onClick={() => setInsightsOf({ id: row.id, code: row.code })}
          >
            <code style={{ direction: 'ltr' }}>{row.code}</code>
          </button>{' '}
          — {row.name_ar}
          {row.holder_name ? (
            <small className="coupon-holder">
              {t('pricing.holder')}: {row.holder_name}
            </small>
          ) : null}
        </span>
      ),
    },
    {
      key: 'value',
      header: t('pricing.discount'),
      align: 'end',
      // ⚠️  The scope rides in this cell rather than a column of its own: "10% — on 5 products"
      //     is one fact, and the table is already seven columns wide at 1280px. The tooltip
      //     lists the first products; the full list is one click away in the edit form.
      render: (row) => (
        <span>
          {row.kind === 'FREE_SHIPPING'
            ? t('couponKind.FREE_SHIPPING')
            : row.kind === 'PERCENTAGE'
              ? `${row.value}%`
              : formatMoney(row.value, i18n.language)}
          <span className="coupon-scope-cell" title={scopeTooltip(row, t, i18n.language)}>
            <Badge
              tone={
                (row.scope_summary?.type ?? 'ALL') === 'ALL' &&
                row.products.length + row.categories.length === 0
                  ? 'neutral'
                  : 'info'
              }
            >
              {scopeLabel(row, t, i18n.language)}
            </Badge>
            {/* Text, not colour: the restriction must be readable without the badge tone */}
            {row.allow_guests === false ? <small>{t('pricing.scope.registeredOnly')}</small> : null}
          </span>
        </span>
      ),
    },
    {
      key: 'usage',
      header: t('pricing.usage'),
      align: 'end',
      secondary: true,
      render: (row) =>
        row.usage_limit ? `${row.usage_count} / ${row.usage_limit}` : row.usage_count,
    },
    {
      key: 'timesUsed',
      header: t('pricing.timesUsed'),
      align: 'end',
      secondary: true,
      render: (row) => row.times_used,
    },
    {
      key: 'netSales',
      header: t('pricing.netSales'),
      align: 'end',
      // ⚠️  Zero is a dash, not "0.00": an unused code and a code that sold nothing
      //     both read as "no sales yet", and a column of zeros looks like a bug.
      render: (row) =>
        row.times_used > 0 ? formatMoney(row.net_sales, i18n.language) : '—',
    },
    {
      key: 'status',
      header: t('admin.status'),
      // ⚠️  Three flags, not one: "disabled" is not enough when the reason
      //     is an expired period or an exhausted limit — and the admin hunts for
      //     a fault that does not exist.
      render: (row) =>
        row.is_running ? (
          <Badge tone="success">{t('pricing.running')}</Badge>
        ) : row.is_exhausted ? (
          <Badge tone="warning">{t('pricing.exhausted')}</Badge>
        ) : row.is_expired ? (
          <Badge tone="neutral">{t('pricing.expired')}</Badge>
        ) : (
          <Badge tone="warning">{t('admin.inactive')}</Badge>
        ),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <ActionMenu
          menuLabel={`${t('admin.actions')} · ${row.code}`}
          items={[
            {
              key: 'edit',
              label: t('common.edit'),
              onSelect: () => setEditingCoupon(row),
            },
            {
              key: 'insights',
              label: t('pricing.insights.open'),
              onSelect: () => setInsightsOf({ id: row.id, code: row.code }),
            },
            // ⚠️  "Usage" appears for used ones alone: a coupon with zero redemptions
            //     opens an empty panel that says nothing.
            {
              key: 'usage',
              label: t('pricing.usage'),
              hidden: row.usage_count === 0,
              onSelect: () => setUsageOf(row),
            },
            // ⚠️  A used one is not deleted — the server answers 409 with a message
            //     counting the uses, and leaving the item out is clearer than a refusal
            //     after the press.
            {
              key: 'delete',
              label: t('common.delete'),
              tone: 'danger',
              hidden: row.usage_count > 0,
              disabled: removeCoupon.isPending,
              onSelect: () =>
                removeCoupon.mutate(row.id, {
                  onSuccess: () => notify(t('pricing.deleted'), 'success'),
                  onError: fail,
                }),
            },
          ]}
        />
      ),
    },
  ];

  const openList = lists.data?.find((row) => row.id === selectedList);

  return (
    <>
      <PageHeader
        title={t('nav.pricing')}
        description={t('pricing.hint')}
        actions={
          <>
            {tab === 'coupons' ? (
              <>
                {couponView === 'list' ? (
                  <Button
                    variant="secondary"
                    loading={exporting}
                    onClick={() => {
                      void exportCoupons();
                    }}
                  >
                    {t('pricing.insights.export')}
                  </Button>
                ) : null}
                <Button variant="secondary" onClick={() => setBulkOpen(true)}>
                  {t('pricing.insights.bulkOpen')}
                </Button>
              </>
            ) : null}
            <Button onClick={() => setCreating(true)}>{t(`pricing.new_${tab}`)}</Button>
          </>
        }
      />

      <StatusTabs
        options={[
          { value: 'lists', label: t('pricing.lists') },
          { value: 'overrides', label: t('pricing.overrides') },
          { value: 'coupons', label: t('pricing.coupons') },
        ]}
        value={tab}
        onChange={(next) => {
          setTab(next as Tab);
          setSelectedList('');
          setSearch('');
          setPage(1);
          closeDrawer();
        }}
      />

      {/* ── Price lists ───────────────────────────── */}
      {tab === 'lists' && !selectedList ? (
        <DataTable
          columns={listColumns}
          rows={lists.data ?? []}
          rowKey={(row) => row.id}
          isLoading={lists.isPending}
          error={lists.error}
          emptyTitle={t('pricing.noLists')}
          emptyBody={t('pricing.noListsBody')}
        />
      ) : null}

      {/* ── An open list's rules ──────────────────── */}
      {tab === 'lists' && selectedList ? (
        <>
          <div className="pricing-crumb">
            <Button size="sm" variant="ghost" onClick={() => setSelectedList('')}>
              ← {t('pricing.backToLists')}
            </Button>
            <strong>{openList?.name_ar}</strong>
          </div>

          <FilterBar hasFilters={Boolean(search)} onClear={() => setSearch('')}>
            <FilterSearch
              value={search}
              onChange={(next) => {
                setSearch(next);
                setPage(1);
              }}
              placeholder={t('admin.searchBySku')}
            />
          </FilterBar>

          <DataTable
            columns={ruleColumns}
            rows={rules.data?.results ?? []}
            rowKey={(row) => row.id}
            isLoading={rules.isPending}
            error={rules.error}
            emptyTitle={t('pricing.noRulesTitle')}
            emptyBody={t('pricing.noRulesBody')}
          />

          {rules.data ? (
            <Pagination page={rules.data.page} pages={rules.data.pages} onChange={setPage} />
          ) : null}
        </>
      ) : null}

      {/* ── Promotional discounts ─────────────────── */}
      {tab === 'overrides' ? (
        <>
          <DataTable
            columns={overrideColumns}
            rows={overrides.data?.results ?? []}
            rowKey={(row) => row.id}
            isLoading={overrides.isPending}
            error={overrides.error}
            emptyTitle={t('pricing.noOverrides')}
            emptyBody={t('pricing.noOverridesBody')}
          />
          {overrides.data ? (
            <Pagination
              page={overrides.data.page}
              pages={overrides.data.pages}
              onChange={setPage}
            />
          ) : null}
        </>
      ) : null}

      {/* ── Coupons ───────────────────────────────── */}
      {tab === 'coupons' ? (
        <>
          {/* ⚠️  Two views of the same coupons, kept in the URL (`?view=report`): the table is
              for managing codes, the report is for reading what they brought in and from whom.
              One period feeds both, so switching view never changes the dates under the reader. */}
          <StatusTabs
            label={t('pricing.report.views')}
            options={[
              { value: 'list', label: t('pricing.report.viewList') },
              { value: 'report', label: t('pricing.report.viewReport') },
            ]}
            value={couponView}
            onChange={(next) => {
              setCouponView(next as (typeof COUPON_VIEWS)[number]);
              setPage(1);
            }}
          />

          <CouponPeriodFilter
            value={period}
            onChange={(next) => {
              setPeriod(next);
              setPage(1);
            }}
          />

          {couponView === 'report' ? (
            <CouponReport period={period} params={periodQuery} onOpen={setInsightsOf} />
          ) : (
            <>
              <CouponStatsBar period={period} params={periodQuery} onOpen={setInsightsOf} />

              <FilterBar
                hasFilters={Boolean(search || couponStatus || couponScope || couponGuests)}
                onClear={() => {
                  setSearch('');
                  setCouponStatus('');
                  setCouponScope('');
                  setCouponGuests('');
                  setPage(1);
                }}
              >
                <FilterSearch
                  value={search}
                  onChange={(next) => {
                    setSearch(next);
                    setPage(1);
                  }}
                  placeholder={t('pricing.searchCoupons')}
                />
                <FilterSelect
                  value={couponStatus}
                  label={t('admin.status')}
                  options={[
                    { value: 'running', label: t('pricing.running') },
                    { value: 'scheduled', label: t('pricing.scheduled') },
                    { value: 'expired', label: t('pricing.expired') },
                  ]}
                  onChange={(next) => {
                    setCouponStatus(next);
                    setPage(1);
                  }}
                />
                <FilterSelect
                  value={couponScope}
                  label={t('pricing.scope.filterLabel')}
                  options={[
                    { value: 'all', label: t('pricing.scope.all') },
                    { value: 'products', label: t('pricing.scope.filterSpecific') },
                    { value: 'categories', label: t('pricing.scope.filterCategories') },
                  ]}
                  onChange={(next) => {
                    setCouponScope(next);
                    setPage(1);
                  }}
                />
                <FilterSelect
                  value={couponGuests}
                  label={t('pricing.scope.filterGuests')}
                  options={[
                    { value: 'allowed', label: t('pricing.scope.guestsAllowed') },
                    { value: 'blocked', label: t('pricing.scope.registeredOnly') },
                  ]}
                  onChange={(next) => {
                    setCouponGuests(next);
                    setPage(1);
                  }}
                />
              </FilterBar>

              <DataTable
                columns={couponColumns}
                rows={coupons.data?.results ?? []}
                rowKey={(row) => row.id}
                isLoading={coupons.isPending}
                error={coupons.error}
                emptyTitle={t('pricing.noCoupons')}
                emptyBody={t('pricing.noCouponsBody')}
              />

              {coupons.data ? (
                <Pagination page={coupons.data.page} pages={coupons.data.pages} onChange={setPage} />
              ) : null}
            </>
          )}
        </>
      ) : null}

      <Drawer
        open={creating || editingList !== null || editingRule !== null || editingCoupon !== null}
        onClose={closeDrawer}
        title={t(`pricing.new_${tab}`)}
      >
        {tab === 'lists' && !selectedList && (creating || editingList) ? (
          <PriceListForm
            key={editingList?.id ?? 'new'}
            {...(editingList ? { list: editingList } : {})}
            onDone={closeDrawer}
          />
        ) : null}

        {tab === 'lists' && selectedList && (creating || editingRule) ? (
          <PriceRuleForm
            key={editingRule?.id ?? 'new'}
            priceListId={selectedList}
            {...(editingRule ? { rule: editingRule } : {})}
            onDone={closeDrawer}
          />
        ) : null}

        {tab === 'overrides' && creating ? (
          <PriceRuleForm key="override" mode="override" onDone={closeDrawer} />
        ) : null}

        {tab === 'coupons' && (creating || editingCoupon) ? (
          <CouponForm
            key={editingCoupon?.id ?? 'new'}
            {...(editingCoupon ? { coupon: editingCoupon } : {})}
            onDone={closeDrawer}
          />
        ) : null}
      </Drawer>

      <Drawer
        open={bulkOpen}
        onClose={() => setBulkOpen(false)}
        title={t('pricing.insights.bulkTitle')}
      >
        {bulkOpen ? <CouponBulkForm onDone={() => setBulkOpen(false)} /> : null}
      </Drawer>

      <CouponInsightsDrawer
        target={insightsOf}
        period={periodQuery}
        onClose={() => setInsightsOf(null)}
      />

      <CouponRedemptionsDrawer coupon={usageOf} onClose={() => setUsageOf(null)} />
    </>
  );
}
