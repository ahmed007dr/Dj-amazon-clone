import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useSaveMailAccount,
  type EmailAccount,
  type MailDirection,
  type MailSecurity,
  type MailTransport,
} from '@/features/mailing/adminApi';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './MailAccountForm.css';

/**
 * The mail account form.
 *
 * ⚠️  **The password field is always presented empty** — the value is never
 *     read from the server at all. And leaving it empty on save means "keep the
 *     current one", not "clear it": editing the port alone would have erased
 *     the password and stopped all mail.
 */
export function MailAccountForm({
  account,
  onDone,
}: {
  account?: EmailAccount;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const save = useSaveMailAccount();

  const [form, setForm] = useState({
    code: account?.code ?? '',
    label_ar: account?.label_ar ?? '',
    label_en: account?.label_en ?? '',
    direction: (account?.direction ?? 'OUT'),
    transport: (account?.transport ?? 'SMTP'),
    host: account?.host ?? '',
    port: account?.port ?? 587,
    security: (account?.security ?? 'TLS'),
    username: account?.username ?? '',
    from_email: account?.from_email ?? '',
    from_name_ar: account?.from_name_ar ?? '',
    from_name_en: account?.from_name_en ?? '',
    reply_to: account?.reply_to ?? '',
    imap_host: account?.imap_host ?? '',
    imap_port: account?.imap_port ?? 993,
    imap_username: account?.imap_username ?? '',
    imap_folder: account?.imap_folder ?? 'INBOX',
    priority: account?.priority ?? 0,
    is_marketing: account?.is_marketing ?? false,
    is_default: account?.is_default ?? false,
    is_active: account?.is_active ?? true,
    password: '',
    imap_password: '',
  });

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState('');

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const receives = form.direction === 'IN' || form.direction === 'BOTH';
  const sends = form.direction === 'OUT' || form.direction === 'BOTH';

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setFieldErrors({});
    setFormError('');

    save.mutate(
      { ...(account ? { id: account.id } : {}), body: form },
      {
        onSuccess: () => {
          notify(t('mail.accountSaved'), 'success');
          onDone();
        },
        onError: (cause) => {
          if (isApiError(cause) && cause.fields) {
            // ⚠️  A field's error is shown **at its field**: a generic message above a
            //     form with twenty fields leaves the operator hunting for the error by eye.
            const mapped: Record<string, string> = {};
            for (const [name, errors] of Object.entries(cause.fields)) {
              const first = errors[0];
              if (first) mapped[name] = first.message;
            }
            setFieldErrors(mapped);
          }
          setFormError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
        },
      },
    );
  };

  return (
    <form className="mail-form" onSubmit={submit}>
      {formError ? <Alert tone="danger">{formError}</Alert> : null}

      <Field
        label={t('mail.code')}
        value={form.code}
        onChange={(event) => set('code', event.target.value)}
        error={fieldErrors['code']}
        required
      />

      <div className="mail-form__row">
        <Field
          label={t('mail.labelAr')}
          value={form.label_ar}
          onChange={(event) => set('label_ar', event.target.value)}
          error={fieldErrors['label_ar']}
          required
        />
        <Field
          label={t('mail.labelEn')}
          value={form.label_en}
          onChange={(event) => set('label_en', event.target.value)}
          error={fieldErrors['label_en']}
          required
        />
      </div>

      <label className="mail-form__select">
        <span>{t('mail.direction')}</span>
        <select
          value={form.direction}
          onChange={(event) => set('direction', event.target.value as MailDirection)}
        >
          <option value="OUT">{t('mail.directionOut')}</option>
          <option value="IN">{t('mail.directionIn')}</option>
          <option value="BOTH">{t('mail.directionBoth')}</option>
        </select>
      </label>

      <label className="mail-form__select">
        <span>{t('mail.transport')}</span>
        <select
          value={form.transport}
          onChange={(event) => set('transport', event.target.value as MailTransport)}
        >
          <option value="SMTP">{t('mail.transportSmtp')}</option>
          <option value="CONSOLE">{t('mail.transportConsole')}</option>
        </select>
      </label>

      {sends && form.transport === 'SMTP' ? (
        <>
          <div className="mail-form__row">
            <Field
              label={t('mail.host')}
              value={form.host}
              onChange={(event) => set('host', event.target.value)}
              error={fieldErrors['host']}
            />
            <Field
              label={t('mail.port')}
              type="number"
              value={form.port}
              onChange={(event) => set('port', Number(event.target.value))}
              error={fieldErrors['port']}
            />
          </div>

          <label className="mail-form__select">
            <span>{t('mail.security')}</span>
            <select
              value={form.security}
              onChange={(event) => set('security', event.target.value as MailSecurity)}
            >
              <option value="TLS">STARTTLS</option>
              <option value="SSL">SSL/TLS</option>
              <option value="NONE">{t('mail.securityNone')}</option>
            </select>
          </label>

          <Field
            label={t('mail.username')}
            value={form.username}
            onChange={(event) => set('username', event.target.value)}
            error={fieldErrors['username']}
          />

          <Field
            label={t('mail.password')}
            type="password"
            value={form.password}
            onChange={(event) => set('password', event.target.value)}
            hint={
              account?.has_password ? t('mail.passwordKeepHint') : t('mail.passwordRequiredHint')
            }
            autoComplete="new-password"
          />
        </>
      ) : null}

      <div className="mail-form__row">
        <Field
          label={t('mail.fromEmail')}
          type="email"
          value={form.from_email}
          onChange={(event) => set('from_email', event.target.value)}
          error={fieldErrors['from_email']}
          required
        />
        <Field
          label={t('mail.replyTo')}
          type="email"
          value={form.reply_to}
          onChange={(event) => set('reply_to', event.target.value)}
          hint={t('mail.replyToHint')}
        />
      </div>

      <div className="mail-form__row">
        <Field
          label={t('mail.fromNameAr')}
          value={form.from_name_ar}
          onChange={(event) => set('from_name_ar', event.target.value)}
        />
        <Field
          label={t('mail.fromNameEn')}
          value={form.from_name_en}
          onChange={(event) => set('from_name_en', event.target.value)}
        />
      </div>

      {receives ? (
        <>
          <div className="mail-form__row">
            <Field
              label={t('mail.imapHost')}
              value={form.imap_host}
              onChange={(event) => set('imap_host', event.target.value)}
              error={fieldErrors['imap_host']}
            />
            <Field
              label={t('mail.imapPort')}
              type="number"
              value={form.imap_port}
              onChange={(event) => set('imap_port', Number(event.target.value))}
            />
          </div>
          <div className="mail-form__row">
            <Field
              label={t('mail.imapUsername')}
              value={form.imap_username}
              onChange={(event) => set('imap_username', event.target.value)}
              hint={t('mail.imapUsernameHint')}
            />
            <Field
              label={t('mail.imapFolder')}
              value={form.imap_folder}
              onChange={(event) => set('imap_folder', event.target.value)}
            />
          </div>
          <Field
            label={t('mail.imapPassword')}
            type="password"
            value={form.imap_password}
            onChange={(event) => set('imap_password', event.target.value)}
            hint={account?.has_imap_password ? t('mail.passwordKeepHint') : ''}
            autoComplete="new-password"
          />
        </>
      ) : null}

      <Field
        label={t('mail.priority')}
        type="number"
        value={form.priority}
        onChange={(event) => set('priority', Number(event.target.value))}
        hint={t('mail.priorityHint')}
      />

      <label className="mail-form__check">
        <input
          type="checkbox"
          checked={form.is_marketing}
          onChange={(event) => set('is_marketing', event.target.checked)}
        />
        <span>
          {t('mail.isMarketing')}
          <small>{t('mail.isMarketingHint')}</small>
        </span>
      </label>

      <label className="mail-form__check">
        <input
          type="checkbox"
          checked={form.is_default}
          onChange={(event) => set('is_default', event.target.checked)}
        />
        <span>
          {t('mail.isDefault')}
          <small>{t('mail.isDefaultHint')}</small>
        </span>
      </label>

      <label className="mail-form__check">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => set('is_active', event.target.checked)}
        />
        <span>{t('mail.isActive')}</span>
      </label>

      {fieldErrors['is_marketing'] ? (
        <Alert tone="danger">{fieldErrors['is_marketing']}</Alert>
      ) : null}

      <Button type="submit" loading={save.isPending} block>
        {t('action.save')}
      </Button>
    </form>
  );
}
