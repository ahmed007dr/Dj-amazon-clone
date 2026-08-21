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
import { CouponForm } from '@/portals/admin/components/CouponForm';
import { CouponRedemptionsDrawer } from '@/portals/admin/components/CouponRedemptionsDrawer';
import { PriceListForm } from '@/portals/admin/components/PriceListForm';
import { PriceRuleForm } from '@/portals/admin/components/PriceRuleForm';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
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
  const [page, setPage] = useState(1);

  const [editingList, setEditingList] = useState<PriceList | null>(null);
  const [editingRule, setEditingRule] = useState<PriceRule | null>(null);
  const [editingCoupon, setEditingCoupon] = useState<Coupon | null>(null);
  const [usageOf, setUsageOf] = useState<Coupon | null>(null);
  const [creating, setCreating] = useState(false);

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
      page,
    },
    tab === 'coupons',
  );

  const removeList = useDeletePriceList();
  const removeRule = useDeletePriceRule();
  const removeOverride = useDeleteOverride();
  const removeCoupon = useDeleteCoupon();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

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
      render: (row) => (
        <span className="pricing-actions">
          <Button size="sm" variant="ghost" onClick={() => setSelectedList(row.id)}>
            {t('pricing.openRules')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditingList(row)}>
            {t('common.edit')}
          </Button>
          {!row.is_default ? (
            <Button
              size="sm"
              variant="ghost"
              loading={removeList.isPending}
              onClick={() =>
                removeList.mutate(row.id, {
                  onSuccess: () => notify(t('pricing.deleted'), 'success'),
                  onError: fail,
                })
              }
            >
              {t('common.delete')}
            </Button>
          ) : null}
        </span>
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
        <span className="pricing-actions">
          <Button size="sm" variant="ghost" onClick={() => setEditingRule(row)}>
            {t('common.edit')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={removeRule.isPending}
            onClick={() =>
              removeRule.mutate(row.id, {
                onSuccess: () => notify(t('pricing.deleted'), 'success'),
                onError: fail,
              })
            }
          >
            {t('common.delete')}
          </Button>
        </span>
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
      render: (row) => (
        <Button
          size="sm"
          variant="ghost"
          loading={removeOverride.isPending}
          onClick={() =>
            removeOverride.mutate(row.id, {
              onSuccess: () => notify(t('pricing.deleted'), 'success'),
              onError: fail,
            })
          }
        >
          {t('common.delete')}
        </Button>
      ),
    },
  ];

  const couponColumns: Column<Coupon>[] = [
    {
      key: 'code',
      header: t('pricing.couponCode'),
      render: (row) => (
        <span>
          <code style={{ direction: 'ltr' }}>{row.code}</code> — {row.name_ar}
        </span>
      ),
    },
    {
      key: 'value',
      header: t('pricing.discount'),
      align: 'end',
      render: (row) =>
        row.kind === 'FREE_SHIPPING'
          ? t('couponKind.FREE_SHIPPING')
          : row.kind === 'PERCENTAGE'
            ? `${row.value}%`
            : formatMoney(row.value, i18n.language),
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
        <span className="pricing-actions">
          <Button size="sm" variant="ghost" onClick={() => setEditingCoupon(row)}>
            {t('common.edit')}
          </Button>

          {/* ⚠️  "Usage" appears for used ones alone: a coupon with zero redemptions
              opens an empty panel that says nothing. */}
          {row.usage_count > 0 ? (
            <Button size="sm" variant="ghost" onClick={() => setUsageOf(row)}>
              {t('pricing.usage')}
            </Button>
          ) : null}
          {/* ⚠️  A used one is not deleted — the server answers 409 with a message
              counting the uses, and hiding the button is clearer than a refusal after the press. */}
          {row.usage_count === 0 ? (
            <Button
              size="sm"
              variant="ghost"
              loading={removeCoupon.isPending}
              onClick={() =>
                removeCoupon.mutate(row.id, {
                  onSuccess: () => notify(t('pricing.deleted'), 'success'),
                  onError: fail,
                })
              }
            >
              {t('common.delete')}
            </Button>
          ) : null}
        </span>
      ),
    },
  ];

  const openList = lists.data?.find((row) => row.id === selectedList);

  return (
    <>
      <PageHeader
        title={t('nav.pricing')}
        description={t('pricing.hint')}
        actions={<Button onClick={() => setCreating(true)}>{t(`pricing.new_${tab}`)}</Button>}
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
          <FilterBar
            hasFilters={Boolean(search || couponStatus)}
            onClear={() => {
              setSearch('');
              setCouponStatus('');
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

      <CouponRedemptionsDrawer coupon={usageOf} onClose={() => setUsageOf(null)} />
    </>
  );
}
