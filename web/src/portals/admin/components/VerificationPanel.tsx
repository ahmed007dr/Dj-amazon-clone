import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DOCUMENT_STATUSES,
  useApproveDocument,
  useBulkApproveDocuments,
  useDocumentCounts,
  useReviewDocuments,
  type DocumentStatus,
  type DocumentType,
  type ReviewDocument,
} from '@/features/academic/verificationApi';
import { DOCUMENT_TYPES } from '@/features/customers/documents';
import { isApiError } from '@/shared/http';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Modal } from '@/shared/ui/Modal';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';
import { formatDate } from '@/shared/utils/format';

import { DocumentPreviewModal } from './DocumentPreviewModal';
import { RejectDocumentModal } from './RejectDocumentModal';

import './AcademicPanels.css';
import './VerificationPanel.css';

const STATUS_TONE = { PENDING: 'warning', APPROVED: 'success', REJECTED: 'danger' } as const;

/**
 * Student verification requests — the review queue.
 *
 * ⚠️  Before this panel, nothing could approve an uploaded student card. The panel
 *     is the first tab of the academic page because it is the only one that is
 *     *work waiting for someone*; the rest is configuration.
 *
 * ⚠️  It is shown whether or not the owner has switched verification **on**.
 *
 *     The switch decides what *students* are told and what they pay; it does not
 *     stop them uploading, so there may always be documents here, and an admin may
 *     always review them. Every other verification notice stays hidden while the
 *     switch is off — this queue is the one exception.
 *
 * ⚠️  Only `PENDING` rows can be selected or decided. A decided document cannot be
 *     decided again (the server answers `409`), so offering the buttons on it would
 *     be offering a button that fails.
 */
export function VerificationPanel() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [status, setStatus] = useState<DocumentStatus>('PENDING');
  const [documentType, setDocumentType] = useState<DocumentType | ''>('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [preview, setPreview] = useState<ReviewDocument | null>(null);
  const [rejecting, setRejecting] = useState<ReviewDocument | null>(null);
  const [confirmingBulk, setConfirmingBulk] = useState(false);

  // ⚠️  The search waits for a pause in typing: a request per keystroke returns
  //     out of order and shows the results of "ahm" after those of "ahmed".
  const term = useDebounced(search.trim());

  const filters = {
    ...(documentType ? { document_type: documentType } : {}),
    ...(term ? { search: term } : {}),
  };

  const list = useReviewDocuments({ status, page, ...filters });
  const counts = useDocumentCounts(true, filters);
  const approve = useApproveDocument();
  const bulk = useBulkApproveDocuments();

  const rows = useMemo(() => list.data?.results ?? [], [list.data]);
  const pendingRows = rows.filter((row) => row.status === 'PENDING');
  const allSelected = pendingRows.length > 0 && pendingRows.every((row) => selected.has(row.id));

  const hasFilters = documentType !== '' || search !== '';

  /** ⚠️  Any change of view clears the selection: ticks must never apply to rows that are no longer on screen. */
  function resetView() {
    setPage(1);
    setSelected(new Set());
  }

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(pendingRows.map((row) => row.id)));
  }

  const fail = (cause: unknown) => {
    notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
  };

  function approveOne(row: ReviewDocument) {
    approve.mutate(row.id, {
      onSuccess: () => {
        notify(t('academic.review.approved'));
        setSelected((current) => {
          const next = new Set(current);
          next.delete(row.id);
          return next;
        });
      },
      onError: fail,
    });
  }

  function approveSelected() {
    bulk.mutate([...selected], {
      onSuccess: (result) => {
        notify(
          result.skipped.length > 0
            ? t('academic.review.bulkPartial', {
                approved: result.approved.length,
                skipped: result.skipped.length,
              })
            : t('academic.review.bulkDone', { approved: result.approved.length }),
        );
        setSelected(new Set());
        setConfirmingBulk(false);
      },
      onError: (cause) => {
        fail(cause);
        setConfirmingBulk(false);
      },
    });
  }

  const columns: Column<ReviewDocument>[] = [
    {
      key: 'select',
      header: t('common.choose'),
      render: (row) =>
        row.status === 'PENDING' ? (
          <input
            type="checkbox"
            className="verification__check"
            checked={selected.has(row.id)}
            aria-label={t('academic.review.selectRow', { name: row.user.name })}
            onChange={() => {
              toggle(row.id);
            }}
          />
        ) : null,
    },
    {
      key: 'student',
      header: t('academic.review.student'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{row.user.name}</strong>
          <code dir="ltr">{row.user.email}</code>
          {row.user.phone ? <code dir="ltr">{row.user.phone}</code> : null}
        </div>
      ),
    },
    {
      key: 'where',
      header: t('academic.review.where'),
      secondary: true,
      render: (row) =>
        row.student ? (
          <div className="academic-cell">
            <strong>{localized(row.student, 'faculty_name')}</strong>
            <code>{localized(row.student, 'university_name')}</code>
          </div>
        ) : (
          <div className="academic-cell">
            <span className="muted">{t('academic.review.noStudentProfile')}</span>
            <code>{t(`accountType.${row.user.account_type}`)}</code>
          </div>
        ),
    },
    {
      key: 'year',
      header: t('academic.academicYear'),
      secondary: true,
      align: 'end',
      render: (row) =>
        row.student ? (
          <div className="academic-cell">
            <span>{t('academic.yearNumber', { count: row.student.academic_year })}</span>
            {row.student.student_number ? (
              <code dir="ltr">{row.student.student_number}</code>
            ) : null}
          </div>
        ) : (
          '—'
        ),
    },
    {
      key: 'document',
      header: t('academic.review.document'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{t(`documentType.${row.document_type}`)}</strong>
          {row.status !== 'PENDING' ? (
            <span>
              <Badge tone={STATUS_TONE[row.status]}>{t(`academic.review.status.${row.status}`)}</Badge>
            </span>
          ) : null}
          {row.status === 'REJECTED' && row.rejection_reason ? (
            <span className="verification__reason muted">{row.rejection_reason}</span>
          ) : null}
          {row.status !== 'PENDING' && row.reviewed_by_name ? (
            <span className="muted verification__reviewer">
              {t('academic.review.reviewedBy', { name: row.reviewed_by_name })}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'submitted',
      header: t('academic.review.submitted'),
      secondary: true,
      render: (row) => formatDate(row.created_at, i18n.language),
    },
    {
      key: 'actions',
      header: t('academic.review.decision'),
      align: 'end',
      render: (row) => (
        <div className="academic-actions">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setPreview(row);
            }}
          >
            {t('academic.review.view')}
          </Button>

          {row.status === 'PENDING' ? (
            <>
              <Button
                size="sm"
                loading={approve.isPending && approve.variables === row.id}
                disabled={approve.isPending}
                onClick={() => {
                  approveOne(row);
                }}
              >
                {t('academic.review.approve')}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => {
                  setRejecting(row);
                }}
              >
                {t('academic.review.reject')}
              </Button>
            </>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <p className="academic-hint">{t('academic.review.hint')}</p>

      <StatusTabs
        label={t('academic.review.tabsLabel')}
        value={status}
        onChange={(next) => {
          setStatus(next as DocumentStatus);
          resetView();
        }}
        options={DOCUMENT_STATUSES.map((value) => ({
          value,
          label: t(`academic.review.status.${value}`),
          ...(counts.data ? { count: counts.data[value] } : {}),
        }))}
      />

      <div className="verification__filters">
        <FilterBar
          hasFilters={hasFilters}
          onClear={() => {
            setDocumentType('');
            setSearch('');
            resetView();
          }}
        >
          <FilterSearch
            value={search}
            placeholder={t('academic.review.searchPlaceholder')}
            onChange={(next) => {
              setSearch(next);
              resetView();
            }}
          />
          <FilterSelect
            label={t('academic.review.allTypes')}
            value={documentType}
            options={DOCUMENT_TYPES.map((value) => ({
              value,
              label: t(`documentType.${value}`),
            }))}
            onChange={(next) => {
              setDocumentType(next as DocumentType | '');
              resetView();
            }}
          />
        </FilterBar>
      </div>

      {pendingRows.length > 0 ? (
        <div className="verification__bulk">
          <label className="academic-check">
            <input type="checkbox" checked={allSelected} onChange={toggleAll} />
            {t('academic.review.selectAll')}
          </label>

          <Button
            disabled={selected.size === 0}
            onClick={() => {
              setConfirmingBulk(true);
            }}
          >
            {t('academic.review.approveSelected', { count: selected.size })}
          </Button>
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={rows}
        isLoading={list.isPending}
        error={list.error}
        rowKey={(row) => row.id}
        emptyTitle={t('academic.review.noRequests')}
        emptyBody={t('academic.review.noRequestsBody')}
      />

      {list.data ? (
        <Pagination
          page={list.data.page}
          pages={list.data.pages}
          onChange={(next) => {
            setPage(next);
            setSelected(new Set());
          }}
        />
      ) : null}

      <DocumentPreviewModal
        key={preview?.id ?? 'none'}
        document={preview}
        onClose={() => {
          setPreview(null);
        }}
      />

      <RejectDocumentModal
        key={rejecting?.id ?? 'none'}
        document={rejecting}
        onClose={() => {
          setRejecting(null);
        }}
      />

      <Modal
        open={confirmingBulk}
        onClose={() => {
          setConfirmingBulk(false);
        }}
        title={t('academic.review.bulkConfirmTitle', { count: selected.size })}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setConfirmingBulk(false);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button loading={bulk.isPending} onClick={approveSelected}>
              {t('academic.review.approve')}
            </Button>
          </>
        }
      >
        <p>{t('academic.review.bulkConfirmBody')}</p>
      </Modal>
    </>
  );
}
