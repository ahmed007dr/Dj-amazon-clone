import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http, saveFile } from '@/shared/http';

/**
 * Mail — the accounts, the responsibilities, the templates and the log.
 *
 * ⚠️  **No field here carries a password in the read direction.**
 *
 *     `password` is written and never read, and the server returns
 *     `has_password` alone. Any field returning the secret — even "partially
 *     masked" — puts it in the browser history, the proxy cache and any open
 *     debugging tool.
 */

export type MailDirection = 'OUT' | 'IN' | 'BOTH';
export type MailTransport = 'SMTP' | 'CONSOLE';
export type MailSecurity = 'NONE' | 'TLS' | 'SSL';

export interface EmailAccount {
  id: string;
  code: string;
  label_ar: string;
  label_en: string;
  direction: MailDirection;
  transport: MailTransport;
  host: string;
  port: number;
  security: MailSecurity;
  username: string;
  timeout: number;
  from_email: string;
  from_name_ar: string;
  from_name_en: string;
  reply_to: string;
  sender: string;
  imap_host: string;
  imap_port: number;
  imap_security: MailSecurity;
  imap_username: string;
  imap_folder: string;
  /** ⚠️  Security messages are never assigned to it — blacklists hit it first. */
  is_marketing: boolean;
  is_default: boolean;
  is_active: boolean;
  priority: number;
  max_per_hour: number;
  /** The secret's status, not its value. */
  has_password: boolean;
  has_imap_password: boolean;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error: string;
  consecutive_failures: number;
  /** An indicator, not a switch: no automatic disabling (ADR-77). */
  is_failing: boolean;
  /**
   * The inbound side's own bookkeeping - read-only, and kept apart from `last_error`
   * (which every successful SMTP send clears) so a working outbound path cannot hide a
   * broken mailbox.
   */
  imap_last_uid: number;
  imap_uidvalidity: number;
  imap_last_fetch_at: string | null;
  imap_last_error: string;
  imap_last_error_at: string | null;
}

/**
 * The address customers should reply to, when there is a mailbox that is actually read.
 *
 * ⚠️  System mail goes out from `noreply@...`, and without a `reply_to` a customer's answer
 *     goes to an address nobody polls. The mailbox an inbound account pulls from is the one
 *     worth pointing replies at: its login when that is an address, otherwise its `from_email`.
 */
export function inboundAddressOf(accounts: EmailAccount[], excludeId?: string): string {
  const mailbox = accounts.find(
    (account) => account.is_active && account.direction !== 'OUT' && account.id !== excludeId,
  );
  if (!mailbox) return '';
  return mailbox.imap_username.includes('@') ? mailbox.imap_username : mailbox.from_email;
}

export type MailPurpose =
  | 'ACCOUNT'
  | 'ORDERS'
  | 'PAYMENTS'
  | 'SHIPPING'
  | 'INVENTORY'
  | 'MARKETING'
  | 'SUPPORT'
  | 'REPORTS'
  | 'SYSTEM';

export interface MailRoute {
  id: string;
  purpose: MailPurpose;
  template_key: string;
  account: string;
  account_code: string;
  account_label_ar: string;
  is_active: boolean;
}

/** Where the account came from — not the result alone. */
export type RoutingSource = 'template' | 'purpose' | 'default' | 'priority' | 'env';

export interface RoutingRow {
  template_key: string;
  purpose: MailPurpose;
  subject_ar: string;
  account_id: string | null;
  account_code: string;
  account_label_ar: string;
  source: RoutingSource;
}

export interface MailTemplate {
  key: string;
  purpose: MailPurpose;
  /** The allowlist: the editor has nothing beyond it. */
  variables: string[];
  subject_ar: string;
  subject_en: string;
  body_ar: string;
  body_en: string;
  is_overridden: boolean;
  is_active: boolean;
  default: {
    subject_ar: string;
    subject_en: string;
    body_ar: string;
    body_en: string;
  };
}

export interface TemplatePreview {
  subject: string;
  body: string;
  unknown_variables: string[];
}

export type DeliveryState = 'PENDING' | 'SENDING' | 'SENT' | 'FAILED' | 'CANCELLED';

export interface OutboundMessage {
  id: string;
  to_email: string;
  subject: string;
  template_key: string;
  purpose: MailPurpose | '';
  language: string;
  status: DeliveryState;
  attempts: number;
  next_attempt_at: string;
  last_error: string;
  sent_at: string | null;
  account: string | null;
  account_code: string;
  created_at: string;
}

export type InboundState = 'NEW' | 'ASSIGNED' | 'REPLIED' | 'CLOSED' | 'SPAM';

/**
 * ⚠️  No `file` field: it used to link to `/media/mail/...`, which the server refuses to serve.
 *     The bytes come from `downloadInboundAttachment`.
 */
export interface InboundAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface InboundMessage {
  id: string;
  account: string;
  account_code: string;
  from_email: string;
  from_name: string;
  to_email: string;
  subject: string;
  body_text: string;
  /** ⚠️  The HTML is stored and never sent — displaying it is XSS on an admin session. */
  has_html: boolean;
  /** The sender's `Date` header - whatever their clock said. */
  received_at: string;
  /** When it reached **our** inbox: this is what the list is ordered by. */
  created_at: string;
  size_bytes: number;
  /** An automated message: replying to it is forbidden — protection against mail loops. */
  is_auto: boolean;
  status: InboundState;
  assigned_to: string | null;
  attachments: InboundAttachment[];
}

export interface Paged<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ═══════════════════════════════════════════════════════════
//  Keys
// ═══════════════════════════════════════════════════════════

const ACCOUNTS = ['admin', 'mail', 'accounts'] as const;
const ROUTES = ['admin', 'mail', 'routes'] as const;
const ROUTING = ['admin', 'mail', 'routing'] as const;
const TEMPLATES = ['admin', 'mail', 'templates'] as const;
const OUTBOX = ['admin', 'mail', 'outbox'] as const;
const INBOX = ['admin', 'mail', 'inbox'] as const;
const INBOX_SUMMARY = ['admin', 'mail', 'inbox-summary'] as const;

/**
 * ⚠️  Every edit invalidates **the map** along with it.
 *
 *     Changing an account or a responsibility flips the answer to "which
 *     account does this template go out from?". And without invalidating it the
 *     operator keeps looking at a stale map saying their assignment did not
 *     apply — so they do it again.
 */
function useMailMutation<TArgs, TResult>(
  run: (args: TArgs) => Promise<TResult>,
  extra: readonly (readonly string[])[] = [],
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ROUTING });
      for (const key of extra) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

// ── Accounts ──────────────────────────────────────────────

export function useMailAccounts() {
  return useQuery({
    queryKey: ACCOUNTS,
    queryFn: () => http.get<EmailAccount[]>('/mailing/admin/accounts/'),
  });
}

export function useSaveMailAccount() {
  return useMailMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<EmailAccount>(`/mailing/admin/accounts/${id}/`, body)
        : http.post<EmailAccount>('/mailing/admin/accounts/', body),
    [ACCOUNTS],
  );
}

export function useDeleteMailAccount() {
  return useMailMutation(
    (id: string) => http.delete<void>(`/mailing/admin/accounts/${id}/`),
    [ACCOUNTS, ROUTES],
  );
}

export interface CheckResult {
  ok: boolean;
  error: string;
  /** An inbound-only account: there is no SMTP to test, and that is not a failure. */
  skipped?: boolean;
}

/** What "Test IMAP" found - nothing was changed in the mailbox. */
export interface ImapCheck {
  ok: boolean;
  error: string;
  folder: string;
  messages: number;
  last_uid: number;
  uidvalidity: number;
  /** Where the pull stands now. */
  cursor: number;
  /** Messages above the cursor: how many the next pull will fetch. */
  pending: number;
}

/** An SMTP handshake with no send — the button that stops the fault being discovered by the first customer. */
export function useVerifyMailAccount() {
  return useMailMutation(
    (id: string) => http.post<CheckResult>(`/mailing/admin/accounts/${id}/verify/`, {}),
    [ACCOUNTS],
  );
}

/**
 * Log in to the mailbox, open the folder, count - the inbound counterpart of the SMTP check.
 *
 * ⚠️  Distinct on purpose: a BOTH account can have a working SMTP and a broken IMAP, and a
 *     green "verified" beside a mailbox nobody can read is how replies went unseen.
 */
export function useTestImap() {
  return useMailMutation(
    (id: string) => http.post<ImapCheck>(`/mailing/admin/accounts/${id}/test-imap/`, {}),
    [ACCOUNTS],
  );
}

export function useSendTestMail() {
  return useMailMutation(
    ({ id, to }: { id: string; to: string }) =>
      http.post<CheckResult>(`/mailing/admin/accounts/${id}/test-send/`, { to }),
    [ACCOUNTS, OUTBOX],
  );
}

// ── Responsibilities ──────────────────────────────────────

export function useMailRoutes() {
  return useQuery({
    queryKey: ROUTES,
    queryFn: () => http.get<MailRoute[]>('/mailing/admin/routes/'),
  });
}

export function useRoutingMap() {
  return useQuery({
    queryKey: ROUTING,
    queryFn: () => http.get<RoutingRow[]>('/mailing/admin/routing/'),
  });
}

export function useSaveMailRoute() {
  return useMailMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<MailRoute>(`/mailing/admin/routes/${id}/`, body)
        : http.post<MailRoute>('/mailing/admin/routes/', body),
    [ROUTES],
  );
}

export function useDeleteMailRoute() {
  return useMailMutation((id: string) => http.delete<void>(`/mailing/admin/routes/${id}/`), [
    ROUTES,
  ]);
}

// ── Templates ─────────────────────────────────────────────

export function useMailTemplates() {
  return useQuery({
    queryKey: TEMPLATES,
    queryFn: () => http.get<MailTemplate[]>('/mailing/admin/templates/'),
  });
}

export function useSaveMailTemplate() {
  return useMailMutation(
    ({ key, body }: { key: string; body: Record<string, unknown> }) =>
      http.put<MailTemplate>(`/mailing/admin/templates/${key}/`, body),
    [TEMPLATES],
  );
}

/** ⚠️  Deleting is "revert to default" — the original text is never lost. */
export function useResetMailTemplate() {
  return useMailMutation(
    (key: string) => http.delete<MailTemplate>(`/mailing/admin/templates/${key}/`),
    [TEMPLATES],
  );
}

export function usePreviewMailTemplate() {
  return useMutation({
    mutationFn: ({ key, body }: { key: string; body: Record<string, unknown> }) =>
      http.post<Record<'ar' | 'en', TemplatePreview>>(
        `/mailing/admin/templates/${key}/preview/`,
        body,
      ),
  });
}

// ── The log and the inbox ─────────────────────────────────

/** A page of a list: the server's `count`/`pages` are for the admin screens alone. */
export interface PagedList<T> extends Paged<T> {
  page: number;
  pages: number;
}

function listPath(base: string, status: string, page: number): string {
  const query = new URLSearchParams();
  if (status) query.set('status', status);
  if (page > 1) query.set('page', String(page));
  const text = query.toString();
  return text ? `${base}?${text}` : base;
}

export function useOutbox(status: string, page = 1) {
  return useQuery({
    queryKey: [...OUTBOX, status, page],
    queryFn: () =>
      http.get<PagedList<OutboundMessage>>(listPath('/mailing/admin/outbox/', status, page)),
    // The previous page stays on screen while the next loads - no flash of an empty table
    placeholderData: keepPreviousData,
  });
}

export function useRetryMessage() {
  return useMailMutation(
    (id: string) => http.post<CheckResult>(`/mailing/admin/outbox/${id}/retry/`, {}),
    [OUTBOX],
  );
}

/**
 * ⚠️  The inbox is the one list here that goes stale while the admin is looking at it.
 *
 *     The app-wide defaults (a minute of freshness, no refetch on focus) suit a catalogue,
 *     not a support queue: a customer replies, the admin is in another tab, comes back and
 *     sees a list that is a minute old and says nothing is new. A short stale time plus a
 *     refetch on focus and a slow poll keeps it honest without hammering the server.
 */
const INBOX_FRESH_MS = 15_000;
const INBOX_POLL_MS = 60_000;

export function useInbox(status: string, page = 1) {
  return useQuery({
    queryKey: [...INBOX, status, page],
    queryFn: () =>
      http.get<PagedList<InboundMessage>>(listPath('/mailing/admin/inbox/', status, page)),
    placeholderData: keepPreviousData,
    staleTime: INBOX_FRESH_MS,
    refetchOnWindowFocus: true,
    refetchInterval: INBOX_POLL_MS,
  });
}

/** The count behind the badge on the tab - a count query, not a page of messages. */
export function useInboxSummary() {
  return useQuery({
    queryKey: INBOX_SUMMARY,
    queryFn: () => http.get<{ new: number }>('/mailing/admin/inbox/summary/'),
    staleTime: INBOX_FRESH_MS,
    refetchOnWindowFocus: true,
    refetchInterval: INBOX_POLL_MS,
  });
}

/**
 * Download an inbound attachment.
 *
 * ⚠️  Through `http.download`, never an `<a href>` to the media folder: the file is served
 *     only to a signed-in admin with the mail permission (and the access is audited), and
 *     `/media/mail/` is blocked outright.
 */
export async function downloadInboundAttachment(messageId: string, attachmentId: string) {
  saveFile(await http.download(`/mailing/admin/inbox/${messageId}/attachments/${attachmentId}/`));
}

export function useUpdateInbound() {
  return useMailMutation(
    ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      http.patch<InboundMessage>(`/mailing/admin/inbox/${id}/`, body),
    [INBOX, INBOX_SUMMARY],
  );
}

export type MailLanguage = 'ar' | 'en';

export function useReplyToInbound() {
  return useMailMutation(
    ({
      id,
      body,
      subject,
      language,
    }: {
      id: string;
      body: string;
      subject?: string;
      language?: MailLanguage;
    }) =>
      http.post<{ queued: boolean; outbound_id: string }>(`/mailing/admin/inbox/${id}/reply/`, {
        body,
        ...(subject ? { subject } : {}),
        ...(language ? { language } : {}),
      }),
    [INBOX, INBOX_SUMMARY, OUTBOX],
  );
}

/**
 * The branded HTML of a message, exactly as it would be sent - before sending it.
 *
 * ⚠️  Nothing is sent or stored. The result is for a **sandboxed iframe** (`srcDoc`,
 *     `sandbox=""`) and nowhere else: it is markup built from text an admin typed.
 */
export function usePreviewMail() {
  return useMutation({
    mutationFn: (body: { subject?: string; body: string; language: MailLanguage }) =>
      http.post<{ html: string }>('/mailing/admin/preview/', body),
  });
}
