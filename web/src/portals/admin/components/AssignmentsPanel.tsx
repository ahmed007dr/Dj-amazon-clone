import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAssignments, type CustomerAssignment } from '@/features/employees/api';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Pagination } from '@/shared/ui/Pagination';

import './AssignmentsPanel.css';

const TONE: Record<string, 'success' | 'neutral' | 'info'> = {
  ACTIVE: 'success',
  ENDED: 'neutral',
  TRANSFERRED: 'info',
};

/**
 * سجل الإسناد.
 *
 * ⚠️  **العمولة تتبع الإسناد — فهذا الجدول مالٌ لا سجل.**
 *
 *     «هذا العميل كان لي في مارس» دعوى تتكرّر كل شهر عند صرف
 *     العمولات، ولا تُحسم إلا بتاريخ الإسناد. شاشة الموظفين تعرض
 *     عدد عملاء كل مندوب اليوم، والعدد لا يقول متى انتقل العميل
 *     ولا من كان قبله.
 *
 * ⚠️  و**المنتهي مُدرَج افتراضيًا**: قصر القائمة على النشط يُلغي
 *     السؤال الوحيد الذي تُفتح لأجله.
 */
export function AssignmentsPanel() {
  const { t } = useTranslation();

  const [activeOnly, setActiveOnly] = useState(false);
  const [page, setPage] = useState(1);

  const query = useAssignments({ ...(activeOnly ? { active: 'true' } : {}), page });

  const columns: Column<CustomerAssignment>[] = [
    {
      key: 'customer',
      header: t('staff.customer'),
      render: (row) => <code dir="ltr">{row.customer_number}</code>,
    },
    {
      key: 'employee',
      header: t('staff.employee'),
      render: (row) => (
        <div className="assignment-cell">
          <strong>{row.employee_name}</strong>
          <code dir="ltr">{row.employee_number}</code>
        </div>
      ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={TONE[row.status] ?? 'neutral'}>
          {t(`staff.assignmentStatus.${row.status}`, { defaultValue: row.status })}
        </Badge>
      ),
    },
    {
      key: 'period',
      header: t('staff.assignedPeriod'),
      align: 'end',
      // ⚠️  الفترة عمود واحد لا عمودان: القارئ يسأل «من متى إلى
      //     متى» سؤالًا واحدًا، وفصلهما يجعله يقارن عمودين.
      render: (row) => (
        <span dir="ltr" className="assignment-period">
          {row.started_at.slice(0, 10)} → {row.ended_at ? row.ended_at.slice(0, 10) : '…'}
        </span>
      ),
    },
  ];

  return (
    <>
      <label className="assignments-toggle">
        <input
          type="checkbox"
          checked={activeOnly}
          onChange={(event) => {
            setActiveOnly(event.target.checked);
            setPage(1);
          }}
        />
        {t('staff.activeOnly')}
      </label>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        rowKey={(row) => row.id}
        isLoading={query.isPending}
        error={query.error}
        emptyTitle={t('staff.noAssignments')}
        emptyBody={t('staff.noAssignmentsBody')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}
    </>
  );
}
