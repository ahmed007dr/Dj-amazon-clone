import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAdminBusinesses, type BusinessProfile } from '@/features/b2b/api';
import { isApiError } from '@/shared/http/errors';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate } from '@/shared/utils/format';

import { CreditPanel } from '../components/CreditPanel';

import './AdminBusinessesPage.css';

const TONE: Record<string, 'success' | 'danger' | 'neutral'> = {
  ACTIVE: 'success',
  SUSPENDED: 'danger',
  NONE: 'neutral',
};

/**
 * الحسابات التجارية وحدودها الائتمانية.
 *
 * ⚠️  **الترخيص المنتهي يُبرَز في القائمة لا في التفاصيل.**
 *
 *     هو أول سبب يمنع الآجل، وأكثر ما يُكتشف بعد أن يُرفض طلب
 *     العميل ويتصل غاضبًا. إظهاره في الصف يجعل المتابعة استباقية.
 */
export function AdminBusinessesPage() {
  const { t, i18n } = useTranslation();

  const [search, setSearch] = useState('');
  const [creditStatus, setCreditStatus] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<BusinessProfile | null>(null);

  const debounced = useDebounced(search);
  const query = useAdminBusinesses({
    ...(debounced ? { search: debounced } : {}),
    ...(creditStatus ? { credit_status: creditStatus } : {}),
    page,
  });

  if (isApiError(query.error) && query.error.status === 403) {
    return (
      <>
        <PageHeader title={t('b2b.businesses')} />
        <StateMessage icon="🔒" title={t('b2b.noAccess')} body={t('b2b.noAccessBody')} />
      </>
    );
  }

  const expired = (row: BusinessProfile) =>
    row.license_expires_on !== null && row.license_expires_on < new Date().toISOString().slice(0, 10);

  const columns: Column<BusinessProfile>[] = [
    {
      key: 'name',
      header: t('b2b.legalName'),
      render: (row) => (
        <div className="business-cell">
          <strong>{row.legal_name}</strong>
          <code>{row.customer_number}</code>
        </div>
      ),
    },
    {
      key: 'kind',
      header: t('b2b.kind'),
      secondary: true,
      render: (row) => t(`b2b.businessKind.${row.kind}`, { defaultValue: row.kind }),
    },
    {
      key: 'licence',
      header: t('b2b.licenseExpiry'),
      secondary: true,
      render: (row) =>
        row.license_expires_on ? (
          <span className={expired(row) ? 'licence-expired' : ''}>
            {formatDate(row.license_expires_on, i18n.language)}
            {expired(row) ? ` · ${t('b2b.expired')}` : ''}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'limit',
      header: t('b2b.creditLimit'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.credit_limit}</span>,
    },
    {
      key: 'terms',
      header: t('b2b.terms'),
      align: 'end',
      secondary: true,
      render: (row) => t('b2b.termsDays', { count: row.payment_terms_days }),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={TONE[row.credit_status] ?? 'neutral'}>
          {t(`b2b.creditStatus.${row.credit_status}`)}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => setSelected(row)}>
          {t('b2b.manage')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t('b2b.businesses')} />

      <FilterBar>
        <FilterSearch
          value={search}
          onChange={(value) => {
            setSearch(value);
            setPage(1);
          }}
          placeholder={t('b2b.searchPlaceholder')}
        />
        <FilterSelect
          label={t('admin.status')}
          value={creditStatus}
          onChange={(value) => {
            setCreditStatus(value);
            setPage(1);
          }}
          options={[
            { value: 'ACTIVE', label: t('b2b.creditStatus.ACTIVE') },
            { value: 'SUSPENDED', label: t('b2b.creditStatus.SUSPENDED') },
            { value: 'NONE', label: t('b2b.creditStatus.NONE') },
          ]}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(row) => row.id}
        emptyTitle={t('b2b.noBusinesses')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        {...(selected ? { title: selected.legal_name } : {})}
      >
        {/* ⚠️  `key` يعيد تركيب اللوح لكل عميل: بلا ذلك تبقى قيم
            النموذج من العميل السابق ظاهرة للحظة — وهي حقول تُمنح
            بها حدود ائتمانية. */}
        {selected ? <CreditPanel key={selected.id} business={selected} /> : null}
      </Drawer>
    </>
  );
}
