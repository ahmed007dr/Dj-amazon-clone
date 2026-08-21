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
 * Payment transactions — reading, capturing and refunding.
 *
 * ⚠️  **Capturing and refunding are financial operations, not a status edit.**
 *
 *     Both genuinely call the gateway. Which is why there is no "change status"
 *     button here: moving it by hand changes nothing at the gateway, and
 *     creates a contradiction between our ledger and theirs with no way to
 *     settle it later.
 */
export function TransactionsPanel() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [status, setStatus] = useState('');
  const [provider, setProvider] = useState('');
  // ⚠️  **Searching by reference is the entire support path.**
  //
  //     The customer says "my order number such-and-such was not paid"; and
  //     without this field the employee scrolls through pages of transactions
  //     until they find it — or fails to and assumes the payment never arrived.
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
      // ⚠️  The refunded amount is always shown, even at zero on a captured transaction:
      //     its absence makes "partially refunded" invisible except by opening the details.
      render: (row) =>
        Number(row.refunded_amount) > 0 ? formatMoney(row.refunded_amount, i18n.language) : '—',
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <span className="tx-actions">
          {/* ⚠️  Capture is for authorised ones alone — and cash on delivery is
              the real case: it is captured on delivery, not before. */}
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

          {/* ⚠️  "Details" for the failed ones first: the table says "failed"
              and the detail says why — and only "gateway unreachable"
              is worth retrying, whereas "insufficient funds" is not. */}
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

            {/* ⚠️  Empty = the full remainder. A pre-filled default made a partial
                refund require clearing the field first — a step that gets
                forgotten, so the full amount is refunded. */}
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

            {/* ⚠️  The failure reason takes its own line: it is what decides whether
                to retry or to call the customer — and the code sits beside the
                message because support searches by the code at the gateway. */}
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
