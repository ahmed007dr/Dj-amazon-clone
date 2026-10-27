import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  downloadInboundAttachment,
  useInbox,
  useInboxSummary,
  useMailAccounts,
  useOutbox,
  useReplyToInbound,
  useRetryMessage,
  type InboundAttachment,
  type InboundMessage,
  type MailLanguage,
  type OutboundMessage,
} from '@/features/mailing/adminApi';
import { MailPreview } from '@/portals/admin/components/MailPreview';
import { isApiError } from '@/shared/http';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { formatDateTime } from '@/shared/utils/format';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Pagination } from '@/shared/ui/Pagination';
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

const INBOUND_TONE: Record<string, 'info' | 'warning' | 'success' | 'neutral' | 'danger'> = {
  NEW: 'warning',
  ASSIGNED: 'info',
  REPLIED: 'success',
  CLOSED: 'neutral',
  SPAM: 'danger',
};

type Side = 'inbox' | 'outbox';

/**
 * A reply goes out in the customer's language by default: Arabic if their message has any
 * Arabic letters in it, English otherwise. It only sets the direction and the footer of
 * the branded layout - the admin can change it before sending.
 */
function guessLanguage(message: InboundMessage): MailLanguage {
  return /[؀-ۿ]/.test(`${message.subject} ${message.body_text}`) ? 'ar' : 'en';
}

function formatSize(bytes: number): string {
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * The log and the inbox.
 *
 * ⚠️  "Did the message go out?" is the first question in every complaint - and
 *     the answer is here, not in a server log read by a developer.
 *
 * ⚠️  **It opens on the inbox.** It used to open on the outbox, where everything looks
 *     healthy, so the one question that mattered - "did the customer's reply arrive?" -
 *     needed two clicks and a guess that the second tab was where to look.
 */
export function MailLogTab() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [side, setSide] = useState<Side>('inbox');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [reading, setReading] = useState<InboundMessage | null>(null);

  const outbox = useOutbox(side === 'outbox' ? status : '', page);
  const inbox = useInbox(side === 'inbox' ? status : '', page);
  const summary = useInboxSummary();
  const accounts = useMailAccounts();
  const retry = useRetryMessage();

  const newCount = summary.data?.new ?? 0;

  // ⚠️  The root cause of "the customer replied and nothing arrived" was often not a bug but
  //     a missing mailbox: replies to system mail go to an address no account ever polls.
  //     Say so on the empty screen instead of leaving an empty table to be misread as "no mail".
  const hasInboundAccount = (accounts.data ?? []).some(
    (account) => account.is_active && account.direction !== 'OUT',
  );
  const missingInbound = side === 'inbox' && accounts.isSuccess && !hasInboundAccount;

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
      key: 'arrived',
      header: t('mail.arrivedAt'),
      render: (row) => formatDateTime(row.created_at, i18n.language),
    },
    {
      key: 'status',
      header: t('mail.status'),
      render: (row) => (
        <Badge tone={INBOUND_TONE[row.status] ?? 'neutral'}>{t(`mail.inbound_${row.status}`)}</Badge>
      ),
    },
    {
      key: 'attachments',
      header: t('mail.attachments'),
      secondary: true,
      render: (row) => row.attachments.length || '—',
    },
  ];

  const changeSide = (next: Side) => {
    setSide(next);
    setStatus('');
    setPage(1);
  };

  const changeStatus = (next: string) => {
    setStatus(next);
    setPage(1);
  };

  const current = side === 'inbox' ? inbox.data : outbox.data;

  return (
    <div className="log">
      <StatusTabs
        options={[
          {
            value: 'inbox',
            label: t('mail.inbox'),
            ...(newCount > 0 ? { count: newCount } : {}),
          },
          { value: 'outbox', label: t('mail.outbox') },
        ]}
        value={side}
        onChange={(next) => {
          changeSide(next as Side);
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
                {
                  value: 'NEW',
                  label: t('mail.inbound_NEW'),
                  ...(newCount > 0 ? { count: newCount } : {}),
                },
                { value: 'ASSIGNED', label: t('mail.inbound_ASSIGNED') },
                { value: 'REPLIED', label: t('mail.inbound_REPLIED') },
                { value: 'CLOSED', label: t('mail.inbound_CLOSED') },
                { value: 'SPAM', label: t('mail.inbound_SPAM') },
              ]
        }
        value={status}
        onChange={changeStatus}
      />

      {missingInbound ? <Alert tone="warning">{t('mail.noInboundAccount')}</Alert> : null}

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
          emptyBody={t('mail.inboxEmptyBody')}
          onRowClick={(row) => {
            setReading(row);
          }}
        />
      )}

      {/* ⚠️  A real page control. The list used to stop at the first 25 rows with nothing to
          say so - older mail was simply unreachable from the screen. */}
      <Pagination page={current?.page ?? page} pages={current?.pages ?? 1} onChange={setPage} />

      <Drawer
        open={reading !== null}
        onClose={() => {
          setReading(null);
        }}
        title={reading?.subject ?? ''}
      >
        {reading ? (
          <InboundReader
            key={reading.id}
            message={reading}
            onSent={() => {
              setReading(null);
            }}
          />
        ) : null}
      </Drawer>
    </div>
  );
}

function InboundReader({ message, onSent }: { message: InboundMessage; onSent: () => void }) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const reply = useReplyToInbound();

  const [body, setBody] = useState('');
  const [language, setLanguage] = useState<MailLanguage>(() => guessLanguage(message));
  const [downloading, setDownloading] = useState('');

  const download = async (attachment: InboundAttachment) => {
    setDownloading(attachment.id);
    try {
      await downloadInboundAttachment(message.id, attachment.id);
    } catch (cause) {
      notify(isApiError(cause) ? cause.displayMessage : t('mail.downloadFailed'), 'danger');
    } finally {
      setDownloading('');
    }
  };

  return (
    <div className="log__reader">
      <p className="log__meta">
        {message.from_name || message.from_email} · {message.from_email}
        {' · '}
        {formatDateTime(message.created_at, i18n.language)}
      </p>

      {/* ⚠️  Plain text alone. The HTML is stored and never reaches the screen:
          a message from a stranger carrying a `script` rendered in an
          admin session is XSS at the highest privilege in the system. */}
      <pre className="log__body">{message.body_text}</pre>

      {message.has_html ? <Alert tone="info">{t('mail.htmlHidden')}</Alert> : null}

      {message.attachments.length > 0 ? (
        <ul className="log__attachments">
          {message.attachments.map((attachment) => (
            <li key={attachment.id}>
              {/* ⚠️  A button styled as a link, not `<a href>`: the file is behind the admin's
                  session and the permission check, so the browser cannot fetch it by URL.
                  It goes through `http.download`, which carries the credentials and turns an
                  error into a message instead of saving the error JSON as the attachment. */}
              <button
                type="button"
                className="log__download"
                disabled={downloading === attachment.id}
                title={t('mail.download')}
                onClick={() => {
                  void download(attachment);
                }}
              >
                {attachment.filename}
              </button>
              <small>
                {attachment.content_type} · {formatSize(attachment.size_bytes)}
              </small>
            </li>
          ))}
        </ul>
      ) : null}

      {message.is_auto ? (
        /* ⚠️  Protection against mail loops: two auto-replies facing each
           other generate thousands of messages and end with the domain
           blacklisted. The block is enforced on the server too. */
        <Alert tone="warning">{t('mail.noReplyToAuto')}</Alert>
      ) : (
        <div className="log__reply">
          <label className="log__field">
            <span>{t('mail.replyBody')}</span>
            <textarea
              rows={6}
              value={body}
              onChange={(event) => {
                setBody(event.target.value);
              }}
            />
          </label>

          <label className="log__field log__field--inline">
            <span>{t('mail.replyLanguage')}</span>
            <select
              value={language}
              onChange={(event) => {
                setLanguage(event.target.value as MailLanguage);
              }}
            >
              <option value="ar">{t('language.ar')}</option>
              <option value="en">{t('language.en')}</option>
            </select>
          </label>

          <MailPreview subject={`Re: ${message.subject}`} body={body} language={language} />

          <Button
            loading={reply.isPending}
            disabled={body.trim().length === 0}
            onClick={() => {
              reply.mutate(
                { id: message.id, body, language },
                {
                  onSuccess: () => {
                    notify(t('mail.replyQueued'), 'success');
                    onSent();
                  },
                  onError: (cause) => {
                    notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
                  },
                },
              );
            }}
          >
            {t('mail.sendReply')}
          </Button>
        </div>
      )}
    </div>
  );
}
