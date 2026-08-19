import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Session } from '@/features/pos/api';
import { useAdminRegisters, useAdminSession, useAdminSessions } from '@/features/pos/adminApi';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { RegistersPanel } from '@/portals/admin/components/RegistersPanel';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';
import { FilterBar, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { formatDate } from '@/shared/utils/format';

import './AdminPosSessionsPage.css';

/**
 * ورديات نقطة البيع.
 *
 * ⚠️  **الشاشة تُقرأ عمود الفرق أولًا — وبُنيت لذلك.**
 *
 *     الأدمن لا يفتحها ليتصفّح الورديات بل ليجد الفرق النقدي غير
 *     الصفري. قائمة تعرض كل شيء بنفس الوزن تدفن الوردية التي بها
 *     عجز مئة جنيه بين ثلاثين وردية متوازنة — فلا يراها أحد حتى
 *     يتكرّر العجز شهرًا.
 */

/** ⚠️  فرق أكبر من هذا يُبرز بصريًا — يوازي `pos.cash_variance_threshold`. */
const NOTABLE_VARIANCE = 20;

export function AdminPosSessionsPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const [status, setStatus] = useState('');
  const [register, setRegister] = useState('');
  const [page, setPage] = useState(1);
  const [detailOf, setDetailOf] = useState<string | null>(null);
  const [view, setView] = useState<'sessions' | 'registers'>('sessions');

  const detail = useAdminSession(detailOf);

  const registers = useAdminRegisters();
  const query = useAdminSessions({
    ...(status ? { status } : {}),
    ...(register ? { register } : {}),
    page,
  });

  const columns: Column<Session>[] = [
    {
      key: 'number',
      header: t('pos.sessionNumber'),
      render: (session) => <strong dir="ltr">{session.number}</strong>,
    },
    {
      key: 'register',
      header: t('pos.register'),
      render: (session) => session.register_code,
    },
    {
      key: 'cashier',
      header: t('pos.cashier'),
      render: (session) => session.cashier_name,
    },
    {
      key: 'opened',
      header: t('pos.openedAt'),
      secondary: true,
      render: (session) => formatDate(session.opened_at, i18n.language),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (session) =>
        session.status === 'OPEN' ? (
          <Badge tone="info">{t('pos.open')}</Badge>
        ) : (
          <Badge tone="neutral">{t('pos.closed')}</Badge>
        ),
    },
    {
      key: 'counted',
      header: t('pos.counted'),
      align: 'end',
      secondary: true,
      // ⚠️  شرطة لا صفر للوردية المفتوحة: الصفر رقم يُقرأ كعدّ
      //     حصل ونتيجته لا شيء، والفارق بينهما هو كل المعنى.
      render: (session) => <span dir="ltr">{session.counted_cash ?? '—'}</span>,
    },
    {
      key: 'variance',
      header: t('pos.variance'),
      align: 'end',
      render: (session) => <VarianceCell session={session} />,
    },
  ];

  return (
    <>
      <PageHeader title={t('pos.sessions')} />

      {/* ⚠️  الكاونترات هنا لا في «النظام»: من يقرأ ورديات فرع هو
          من يضيف كاونتره الثاني ويوقف المعطّل — وفصلهما يجعل
          فتح فرع جديد رحلة بين شاشتين. */}
      <div className="pos-view-tabs" role="tablist">
        {(['sessions', 'registers'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={view === value}
            className={view === value ? 'is-active' : ''}
            onClick={() => setView(value)}
          >
            {t(`pos.view.${value}`)}
          </button>
        ))}
      </div>

      {view === 'registers' ? <RegistersPanel /> : null}

      {view === 'sessions' ? (
      <>
      <FilterBar>
        <FilterSelect
          label={t('admin.status')}
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          // ⚠️  بلا خيار «الكل»: `FilterSelect` تضعه بنفسها
          //     كخيار فارغ يحمل التسمية — وإضافته هنا تكرّره.
          options={[
            { value: 'OPEN', label: t('pos.open') },
            { value: 'CLOSED', label: t('pos.closed') },
          ]}
        />

        <FilterSelect
          label={t('pos.register')}
          value={register}
          onChange={(value) => {
            setRegister(value);
            setPage(1);
          }}
          options={(registers.data ?? []).map((row) => ({
            value: row.id,
            label: localized(row, 'name'),
          }))}
        />
      </FilterBar>

      <DataTable
        columns={[
          ...columns,
          {
            key: 'actions',
            header: '',
            align: 'end',
            // ⚠️  التفصيل يُطلَب ولا يُجلب لكل صفّ: الصفحة تعرض
            //     عشرين وردية وتُقرأ منها واحدة.
            render: (row) => (
              <Button size="sm" variant="ghost" onClick={() => setDetailOf(row.id)}>
                {t('pos.sessionDetail')}
              </Button>
            ),
          },
        ]}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(session) => session.id}
        emptyTitle={t('pos.noSessions')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}
      </>
      ) : null}

      <Drawer
        open={detailOf !== null}
        onClose={() => setDetailOf(null)}
        {...(detail.data ? { title: detail.data.number } : {})}
      >
        {detail.isPending ? (
          <Spinner />
        ) : detail.data ? (
          <dl className="session-detail">
            {(
              [
                ['pos.register', detail.data.register_code],
                ['pos.cashier', detail.data.cashier_name],
                ['pos.openingFloat', detail.data.opening_float],
                ['pos.countedCash', detail.data.counted_cash ?? '—'],
                ['pos.expectedCash', detail.data.expected_cash ?? '—'],
                ['pos.variance', detail.data.variance ?? '—'],
              ] as const
            ).map(([key, value]) => (
              <div key={key}>
                <dt>{t(key)}</dt>
                <dd dir="ltr">{value}</dd>
              </div>
            ))}

            {/* ⚠️  تفسير الفرق هو المحتوى لا حاشية: وردية بفرق
                بلا تفسير هي بالضبط ما تبحث عنه المراجعة. */}
            {detail.data.variance_note ? (
              <div className="session-detail__note">
                <dt>{t('pos.varianceNote')}</dt>
                <dd>{detail.data.variance_note}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </Drawer>
    </>
  );
}

/**
 * خلية الفرق.
 *
 * ⚠️  **اللون ليس وحده الإشارة.**
 *
 *     أحمر بلا نص يختفي تمامًا على من لا يميّز الألوان — وهي
 *     الحالة التي يُفترض أن تُلتقط بنظرة. الإشارة هنا اللون
 *     **والخط العريض والعلامة** معًا.
 */
function VarianceCell({ session }: { session: Session }) {
  if (session.variance === null) return <span>—</span>;

  const value = Number(session.variance);
  const notable = Math.abs(value) >= NOTABLE_VARIANCE;

  return (
    <span
      dir="ltr"
      className={`pos-variance ${notable ? 'is-notable' : ''} ${
        value < 0 ? 'is-short' : ''
      }`}
    >
      {value > 0 ? `+${session.variance}` : session.variance}
    </span>
  );
}
