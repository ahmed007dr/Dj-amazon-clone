import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  listProviders,
  listTransactions,
  useCaptureTransaction,
  useRefundTransaction,
  useTransaction,
  type PaymentTransaction,
} from '@/features/payments/adminApi';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Drawer } from '@/shared/ui/Drawer';
import { Modal } from '@/shared/ui/Modal';
import { Pagination } from '@/shared/ui/Pagination';
import { useToast } from '@/shared/ui/useToast';
import { formatDateTime, formatMoney } from '@/shared/utils/format';

import './TransactionsPanel.css';

const TONES = {
  PENDING: 'warning',
  AUTHORIZED: 'info',
  CAPTURED: 'success',
  FAILED: 'danger',
  CANCELLED: 'neutral',
  REFUNDED: 'neutral',
} as const;

/**
 * معاملات الدفع — قراءةً وتحصيلًا واستردادًا.
 *
 * ⚠️  **التحصيل والاسترداد عمليتان ماليتان لا تعديل حالة.**
 *
 *     كلاهما ينادي البوابة فعلًا. ولذلك لا يوجد هنا زر «تغيير
 *     الحالة»: تحريكها يدويًا لا يغيّر شيئًا لدى البوابة، ويخلق
 *     تناقضًا بين دفترنا ودفترها لا طريقة لحسمه لاحقًا.
 */
export function TransactionsPanel() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [status, setStatus] = useState('');
  const [provider, setProvider] = useState('');
  // ⚠️  **البحث بالمرجع هو مسار الدعم كله.**
  //
  //     العميل يقول «طلبي رقم كذا لم يُدفع»؛ وبلا هذا الحقل يمرّر
  //     الموظف في صفحات المعاملات حتى يجده — أو لا يجده فيفترض
  //     أن الدفع لم يصل.
  const [reference, setReference] = useState('');
  const [page, setPage] = useState(1);
  const [refunding, setRefunding] = useState<PaymentTransaction | null>(null);
  const [inspecting, setInspecting] = useState<string | null>(null);

  const detail = useTransaction(inspecting);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');

  const debouncedReference = useDebounced(reference);

  const providers = useQuery({
    queryKey: ['admin', 'payment-providers'],
    queryFn: listProviders,
    staleTime: 30 * 60 * 1000,
  });

  const query = useQuery({
    queryKey: ['admin', 'transactions', status, provider, debouncedReference, page],
    queryFn: () =>
      listTransactions({
        ...(status ? { status } : {}),
        ...(provider ? { provider } : {}),
        ...(debouncedReference ? { reference_id: debouncedReference } : {}),
        page,
      }),
    staleTime: 30 * 1000,
  });

  const capture = useCaptureTransaction();
  const refund = useRefundTransaction();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const closeRefund = () => {
    setRefunding(null);
    setAmount('');
    setReason('');
  };

  const columns: Column<PaymentTransaction>[] = [
    {
      key: 'created',
      header: t('admin.createdAt'),
      render: (row) => formatDateTime(row.created_at, i18n.language),
    },
    {
      key: 'reference',
      header: t('payments.reference'),
      render: (row) => <code style={{ direction: 'ltr' }}>{row.reference}</code>,
    },
    {
      key: 'provider',
      header: t('admin.adapter'),
      secondary: true,
      render: (row) => row.provider_code,
    },
    {
      key: 'amount',
      header: t('payments.amount'),
      align: 'end',
      render: (row) => formatMoney(row.amount, i18n.language),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={TONES[row.status] ?? 'neutral'}>{t(`transactionStatus.${row.status}`)}</Badge>
      ),
    },
    {
      key: 'refunded',
      header: t('payments.refunded'),
      align: 'end',
      secondary: true,
      // ⚠️  المسترد يظهر دائمًا ولو كان صفرًا في معاملة محصَّلة:
      //     غيابه يجعل «مسترد جزئيًا» غير مرئي إلا بفتح التفاصيل.
      render: (row) =>
        Number(row.refunded_amount) > 0 ? formatMoney(row.refunded_amount, i18n.language) : '—',
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <span className="tx-actions">
          {/* ⚠️  التحصيل للمُصرَّح وحده — والدفع عند الاستلام هو
              الحالة الحقيقية: يُحصَّل عند التسليم لا قبله. */}
          {row.status === 'AUTHORIZED' ? (
            <Button
              size="sm"
              variant="secondary"
              loading={capture.isPending}
              onClick={() =>
                capture.mutate(row.id, {
                  onSuccess: () => notify(t('payments.captured'), 'success'),
                  onError: fail,
                })
              }
            >
              {t('payments.capture')}
            </Button>
          ) : null}

          {Number(row.refundable_amount) > 0 ? (
            <Button size="sm" variant="ghost" onClick={() => setRefunding(row)}>
              {t('payments.refund')}
            </Button>
          ) : null}

          {/* ⚠️  «التفاصيل» للفاشلة أولًا: الجدول يقول «فشلت»
              والتفصيل يقول لماذا — و«انقطاع عن البوابة» وحده
              يستحق إعادة المحاولة، أما «رصيد غير كافٍ» فلا. */}
          <Button size="sm" variant="ghost" onClick={() => setInspecting(row.id)}>
            {t('payments.details')}
          </Button>
        </span>
      ),
    },
  ];

  return (
    <>
      <FilterBar
        hasFilters={Boolean(status || provider || reference)}
        onClear={() => {
          setStatus('');
          setProvider('');
          setReference('');
          setPage(1);
        }}
      >
        <FilterSearch
          value={reference}
          onChange={(next) => {
            setReference(next);
            setPage(1);
          }}
          placeholder={t('payments.searchByReference')}
        />

        <FilterSelect
          value={provider}
          label={t('payments.provider')}
          options={(providers.data ?? []).map((row) => ({
            value: row.id,
            label: row.name_ar || row.code,
          }))}
          onChange={(next) => {
            setProvider(next);
            setPage(1);
          }}
        />

        <FilterSelect
          value={status}
          label={t('admin.status')}
          options={Object.keys(TONES).map((value) => ({
            value,
            label: t(`transactionStatus.${value}`),
          }))}
          onChange={(next) => {
            setStatus(next);
            setPage(1);
          }}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        rowKey={(row) => row.id}
        isLoading={query.isPending}
        error={query.error}
        emptyTitle={t('payments.noTransactions')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Modal
        open={refunding !== null}
        onClose={closeRefund}
        title={t('payments.refundTitle')}
        footer={
          <>
            <Button
              variant="danger"
              loading={refund.isPending}
              disabled={reason.trim().length < 3}
              onClick={() => {
                if (!refunding) return;
                refund.mutate(
                  { id: refunding.id, ...(amount ? { amount } : {}), reason },
                  {
                    onSuccess: () => {
                      notify(t('payments.refunded_done'), 'success');
                      closeRefund();
                    },
                    onError: fail,
                  },
                );
              }}
            >
              {t('payments.refund')}
            </Button>
            <Button variant="ghost" onClick={closeRefund}>
              {t('common.cancel')}
            </Button>
          </>
        }
      >
        {refunding ? (
          <div className="tx-refund">
            <p>
              {t('payments.refundableIs', {
                amount: formatMoney(refunding.refundable_amount, i18n.language),
              })}
            </p>

            {/* ⚠️  فارغ = كامل المتبقي. الافتراضي المملوء مسبقًا كان
                يجعل الاسترداد الجزئي يحتاج مسح الحقل أولًا — وهي
                خطوة تُنسى فيُردّ المبلغ كاملًا. */}
            <Field
              label={t('payments.refundAmount')}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              inputMode="decimal"
              dir="ltr"
              hint={t('payments.refundAmountHint')}
            />

            <label className="tx-refund__reason">
              <span>
                {t('payments.refundReason')}
                <em aria-hidden> *</em>
              </span>
              <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>
        ) : null}
      </Modal>

      <Drawer
        open={inspecting !== null}
        onClose={() => setInspecting(null)}
        {...(detail.data ? { title: detail.data.reference } : {})}
      >
        {detail.data ? (
          <dl className="tx-detail">
            {(
              [
                ['payments.provider', detail.data.provider_code],
                ['payments.method', detail.data.method],
                ['admin.status', t(`transactionStatus.${detail.data.status}`, { defaultValue: detail.data.status })],
                ['payments.amount', detail.data.amount],
                ['payments.refunded', detail.data.refunded_amount],
                ['payments.providerReference', detail.data.provider_reference || '—'],
                ['payments.referenceId', detail.data.reference_id || '—'],
              ] as const
            ).map(([key, value]) => (
              <div key={key}>
                <dt>{t(key)}</dt>
                <dd dir="ltr">{value}</dd>
              </div>
            ))}

            {/* ⚠️  سبب الفشل يأخذ سطره: هو ما يقرّر أتُعاد المحاولة
                أم يُتصل بالعميل — والرمز بجوار الرسالة لأن الدعم
                يبحث بالرمز لدى البوابة. */}
            {detail.data.failure_message || detail.data.failure_code ? (
              <div className="tx-detail__failure">
                <dt>{t('payments.failureReason')}</dt>
                <dd>
                  {detail.data.failure_message || '—'}
                  {detail.data.failure_code ? (
                    <code dir="ltr">{detail.data.failure_code}</code>
                  ) : null}
                </dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </Drawer>
    </>
  );
}
