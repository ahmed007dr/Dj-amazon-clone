import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * البريد — الحسابات والمسؤوليات والقوالب والسجل.
 *
 * ⚠️  **لا حقل هنا يحمل كلمة مرور في اتجاه القراءة.**
 *
 *     `password` يُكتب ولا يُقرأ، والخادم يعيد `has_password` وحده.
 *     أي حقل يعيد السرّ — ولو «مقنّعًا جزئيًا» — يضعه في سجل المتصفح
 *     وكاش الوكيل وأي أداة تصحيح مفتوحة.
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
  /** ⚠️  لا تُسنَد إليه رسائل الأمان — القوائم السوداء تصيبه أولًا. */
  is_marketing: boolean;
  is_default: boolean;
  is_active: boolean;
  priority: number;
  max_per_hour: number;
  /** حالة السرّ لا قيمته. */
  has_password: boolean;
  has_imap_password: boolean;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error: string;
  consecutive_failures: number;
  /** مؤشّر لا مفتاح: لا إيقاف تلقائي (ADR-77). */
  is_failing: boolean;
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

/** من أين جاء الحساب — لا النتيجة وحدها. */
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
  /** قائمة السماح: المحرّر لا يملك غيرها. */
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

export interface InboundAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  file: string;
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
  /** ⚠️  الـ HTML مخزَّن ولا يُرسَل — عرضه XSS على جلسة أدمن. */
  has_html: boolean;
  received_at: string;
  size_bytes: number;
  /** رسالة آلية: الردّ عليها ممنوع — حماية من حلقات البريد. */
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
//  المفاتيح
// ═══════════════════════════════════════════════════════════

const ACCOUNTS = ['admin', 'mail', 'accounts'] as const;
const ROUTES = ['admin', 'mail', 'routes'] as const;
const ROUTING = ['admin', 'mail', 'routing'] as const;
const TEMPLATES = ['admin', 'mail', 'templates'] as const;
const OUTBOX = ['admin', 'mail', 'outbox'] as const;
const INBOX = ['admin', 'mail', 'inbox'] as const;

/**
 * ⚠️  كل تعديل يُبطل **الخريطة** معه.
 *
 *     تغيير حساب أو مسؤولية يقلب الجواب على «من أي حساب يخرج هذا
 *     القالب؟». وبلا إبطالها يبقى المشغّل ينظر إلى خريطة قديمة
 *     تقول إن إسناده لم يُطبَّق — فيعيده مرة أخرى.
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

// ── الحسابات ───────────────────────────────────────────────

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
}

/** مصافحة SMTP بلا إرسال — الزرّ الذي يمنع اكتشاف الخطأ بعد أول عميل. */
export function useVerifyMailAccount() {
  return useMailMutation(
    (id: string) => http.post<CheckResult>(`/mailing/admin/accounts/${id}/verify/`, {}),
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

// ── المسؤوليات ─────────────────────────────────────────────

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

// ── القوالب ────────────────────────────────────────────────

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

/** ⚠️  الحذف هو «الرجوع إلى الافتراضي» — لا فقدان للنص الأصلي. */
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

// ── السجل والوارد ──────────────────────────────────────────

export function useOutbox(status: string) {
  return useQuery({
    queryKey: [...OUTBOX, status],
    queryFn: () =>
      http.get<Paged<OutboundMessage>>(
        status ? `/mailing/admin/outbox/?status=${status}` : '/mailing/admin/outbox/',
      ),
  });
}

export function useRetryMessage() {
  return useMailMutation(
    (id: string) => http.post<CheckResult>(`/mailing/admin/outbox/${id}/retry/`, {}),
    [OUTBOX],
  );
}

export function useInbox(status: string) {
  return useQuery({
    queryKey: [...INBOX, status],
    queryFn: () =>
      http.get<Paged<InboundMessage>>(
        status ? `/mailing/admin/inbox/?status=${status}` : '/mailing/admin/inbox/',
      ),
  });
}

export function useUpdateInbound() {
  return useMailMutation(
    ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      http.patch<InboundMessage>(`/mailing/admin/inbox/${id}/`, body),
    [INBOX],
  );
}

export function useReplyToInbound() {
  return useMailMutation(
    ({ id, body, subject }: { id: string; body: string; subject?: string }) =>
      http.post<{ queued: boolean; outbound_id: string }>(`/mailing/admin/inbox/${id}/reply/`, {
        body,
        ...(subject ? { subject } : {}),
      }),
    [INBOX, OUTBOX],
  );
}
