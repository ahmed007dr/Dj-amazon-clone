import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useInbox,
  useOutbox,
  useReplyToInbound,
  useRetryMessage,
  type InboundMessage,
  type OutboundMessage,
} from '@/features/mailing/adminApi';
import { isApiError } from '@/shared/http';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';

import './MailLogTab.css';

const STATE_TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  SENT: 'success',
  PENDING: 'warning',
  SENDING: 'warning',
  FAILED: 'danger',
  CANCELLED: 'neutral',
};

/**
 * السجل والوارد.
 *
 * ⚠️  «هل خرجت الرسالة؟» أول سؤال في كل شكوى — والجواب هنا لا في
 *     سجل خادم يقرأه مطوّر.
 */
export function MailLogTab() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [side, setSide] = useState<'outbox' | 'inbox'>('outbox');
  const [status, setStatus] = useState('');
  const [reading, setReading] = useState<InboundMessage | null>(null);
  const [replyBody, setReplyBody] = useState('');

  const outbox = useOutbox(side === 'outbox' ? status : '');
  const inbox = useInbox(side === 'inbox' ? status : '');
  const retry = useRetryMessage();
  const reply = useReplyToInbound();

  const outboxColumns: Column<OutboundMessage>[] = [
    { key: 'to', header: t('mail.recipient'), render: (row) => row.to_email },
    {
      key: 'subject',
      header: t('mail.subject'),
      render: (row) => <span className="log__subject">{row.subject}</span>,
    },
    {
      key: 'status',
      header: t('mail.status'),
      render: (row) => (
        <Badge tone={STATE_TONE[row.status] ?? 'neutral'}>{t(`mail.state_${row.status}`)}</Badge>
      ),
    },
    {
      key: 'attempts',
      header: t('mail.attempts'),
      secondary: true,
      render: (row) => row.attempts,
    },
    {
      key: 'action',
      header: '',
      align: 'end',
      render: (row) =>
        row.status === 'FAILED' ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              retry.mutate(row.id, {
                onSuccess: (result) =>
                  notify(
                    result.ok ? t('mail.retrySucceeded') : t('mail.retryFailed'),
                    result.ok ? 'success' : 'danger',
                  ),
                onError: (cause) =>
                  notify(
                    isApiError(cause) ? cause.displayMessage : t('mail.retryFailed'),
                    'danger',
                  ),
              })
            }
          >
            {t('mail.retry')}
          </Button>
        ) : null,
    },
  ];

  const inboxColumns: Column<InboundMessage>[] = [
    {
      key: 'from',
      header: t('mail.sender'),
      render: (row) => (
        <div className="log__from">
          <span>{row.from_name || row.from_email}</span>
          {row.is_auto ? <Badge tone="neutral">{t('mail.auto')}</Badge> : null}
        </div>
      ),
    },
    {
      key: 'subject',
      header: t('mail.subject'),
      render: (row) => <span className="log__subject">{row.subject}</span>,
    },
    {
      key: 'status',
      header: t('mail.status'),
      render: (row) => <Badge tone="info">{t(`mail.inbound_${row.status}`)}</Badge>,
    },
    {
      key: 'attachments',
      header: t('mail.attachments'),
      secondary: true,
      render: (row) => row.attachments.length || '—',
    },
  ];

  return (
    <div className="log">
      <StatusTabs
        options={[
          { value: 'outbox', label: t('mail.outbox') },
          { value: 'inbox', label: t('mail.inbox') },
        ]}
        value={side}
        onChange={(next) => {
          setSide(next as 'outbox' | 'inbox');
          setStatus('');
        }}
      />

      <StatusTabs
        options={
          side === 'outbox'
            ? [
                { value: '', label: t('mail.all') },
                { value: 'PENDING', label: t('mail.state_PENDING') },
                { value: 'SENT', label: t('mail.state_SENT') },
                { value: 'FAILED', label: t('mail.state_FAILED') },
              ]
            : [
                { value: '', label: t('mail.all') },
                { value: 'NEW', label: t('mail.inbound_NEW') },
                { value: 'REPLIED', label: t('mail.inbound_REPLIED') },
                { value: 'CLOSED', label: t('mail.inbound_CLOSED') },
              ]
        }
        value={status}
        onChange={setStatus}
      />

      {side === 'outbox' ? (
        <DataTable
          columns={outboxColumns}
          rows={outbox.data?.results ?? []}
          rowKey={(row) => row.id}
          isLoading={outbox.isPending}
          error={outbox.error}
          emptyTitle={t('mail.outboxEmpty')}
        />
      ) : (
        <DataTable
          columns={inboxColumns}
          rows={inbox.data?.results ?? []}
          rowKey={(row) => row.id}
          isLoading={inbox.isPending}
          error={inbox.error}
          emptyTitle={t('mail.inboxEmpty')}
          onRowClick={(row) => {
            setReading(row);
            setReplyBody('');
          }}
        />
      )}

      <Drawer
        open={reading !== null}
        onClose={() => setReading(null)}
        title={reading?.subject ?? ''}
      >
        {reading ? (
          <div className="log__reader">
            <p className="log__meta">
              {reading.from_name || reading.from_email} · {reading.from_email}
            </p>

            {/* ⚠️  النص الصريح وحده. الـ HTML مخزَّن ولا يصل الشاشة:
                رسالة من مجهول تحمل `script` تُعرَض في جلسة أدمن هي
                XSS على أعلى صلاحية في النظام. */}
            <pre className="log__body">{reading.body_text}</pre>

            {reading.has_html ? <Alert tone="info">{t('mail.htmlHidden')}</Alert> : null}

            {reading.attachments.length > 0 ? (
              <ul className="log__attachments">
                {reading.attachments.map((attachment) => (
                  <li key={attachment.id}>
                    {attachment.filename}
                    <small>{attachment.content_type}</small>
                  </li>
                ))}
              </ul>
            ) : null}

            {reading.is_auto ? (
              /* ⚠️  حماية من حلقات البريد: ردّان آليان متقابلان
                 يولّدان آلاف الرسائل وينتهيان بالدومين في القوائم
                 السوداء. المنع مفروض في الخادم أيضًا. */
              <Alert tone="warning">{t('mail.noReplyToAuto')}</Alert>
            ) : (
              <div className="log__reply">
                <label className="log__field">
                  <span>{t('mail.replyBody')}</span>
                  <textarea
                    rows={6}
                    value={replyBody}
                    onChange={(event) => setReplyBody(event.target.value)}
                  />
                </label>

                <Button
                  loading={reply.isPending}
                  disabled={replyBody.trim().length === 0}
                  onClick={() =>
                    reply.mutate(
                      { id: reading.id, body: replyBody },
                      {
                        onSuccess: () => {
                          notify(t('mail.replyQueued'), 'success');
                          setReading(null);
                        },
                        onError: (cause) =>
                          notify(
                            isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                            'danger',
                          ),
                      },
                    )
                  }
                >
                  {t('mail.sendReply')}
                </Button>
              </div>
            )}
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
