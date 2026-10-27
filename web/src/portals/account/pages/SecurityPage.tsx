import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { changePassword } from '@/features/auth/api';
import { EmailChangeForm } from '@/portals/account/components/EmailChangeForm';
import { SessionList } from '@/portals/account/components/SessionList';
import { useAuth } from '@/features/auth/useAuth';
import { useTabParam } from '@/shared/hooks/useTabParam';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { TabPanel } from '@/shared/ui/TabPanel';

import './SecurityPage.css';

const TABS = ['password', 'email', 'devices'] as const;

/**
 * Security — the password, the email and the connected devices.
 *
 * ⚠️  Three tabs rather than one stacked page.
 *
 *     The three had nothing in common but the word "security", and stacking them
 *     put the rarest, most alarming action (ending a device's session) under the
 *     longest form. Each tab is in the URL (`?tab=email`), so support can link
 *     straight to the one the user needs.
 *
 * ⚠️  The tabs are **not kept mounted** — and that is deliberate here.
 *
 *     The password fields live in the first tab; unmounting it when the user
 *     leaves clears what they typed. A password left sitting in a hidden form
 *     is exactly what should not survive a trip to another tab.
 *
 * ⚠️  Changing the password **ends every session**, including this one.
 *
 *     Said before the press rather than after: a user who suddenly finds
 *     themselves logged out assumes something broke, and retries with a
 *     password they have started to doubt.
 */
export function SecurityPage() {
  const { t } = useTranslation();
  const { signOut } = useAuth();
  const [tab, setTab] = useTabParam(TABS, 'password');

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;

    setError(null);
    setFieldErrors({});
    setPending(true);

    try {
      await changePassword(current, next);
      setDone(true);
      // The sessions were ended on the server — the local cleanup keeps the state consistent
      await signOut();
    } catch (cause) {
      if (isApiError(cause)) {
        setError(cause.displayMessage);
        setFieldErrors({
          current_password: cause.fieldError('current_password') ?? '',
          new_password: cause.fieldError('new_password') ?? '',
        });
      } else {
        setError(t('state.errorTitle'));
      }
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <>
        <PageHeader title={t('account.security')} />
        <Alert tone="success">{t('account.passwordChangedSignOut')}</Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('account.security')} />

      <StatusTabs
        id="security"
        label={t('account.securityTabsLabel')}
        value={tab}
        onChange={(next) => {
          setTab(next as (typeof TABS)[number]);
        }}
        options={[
          { value: 'password', label: t('account.securityTab.password') },
          { value: 'email', label: t('account.securityTab.email') },
          { value: 'devices', label: t('account.securityTab.devices') },
        ]}
      />

      {/* ── Password ───────────────────────────────── */}
      <TabPanel id="security" value="password" active={tab === 'password'}>
        <form
          className="surface security"
          onSubmit={(event) => void handleSubmit(event)}
          noValidate
        >
          <h2 className="security__title">{t('auth.changePassword')}</h2>

          {error ? <Alert tone="danger">{error}</Alert> : null}

          {/* The warning before the press, not after */}
          <Alert tone="warning">{t('account.changePasswordWarning')}</Alert>

          <Field
            label={t('auth.currentPassword')}
            type="password"
            autoComplete="current-password"
            required
            value={current}
            error={fieldErrors.current_password || undefined}
            onChange={(event) => {
              setCurrent(event.target.value);
            }}
          />

          <Field
            label={t('auth.newPassword')}
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={next}
            hint={t('auth.passwordHint')}
            error={fieldErrors.new_password || undefined}
            onChange={(event) => {
              setNext(event.target.value);
            }}
          />

          <Field
            label={t('auth.confirmPassword')}
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            error={mismatch ? t('auth.passwordMismatch') : undefined}
            onChange={(event) => {
              setConfirm(event.target.value);
            }}
          />

          <Button type="submit" loading={pending} disabled={mismatch || !next || !current}>
            {t('auth.changePassword')}
          </Button>
        </form>
      </TabPanel>

      {/* ── Email ──────────────────────────────────── */}
      {/* ⚠️  A card of the same width as the password one. The form used to sit
          bare in a flex column, so its button stretched to the full page width. */}
      <TabPanel id="security" value="email" active={tab === 'email'}>
        <section className="surface security">
          <h2 className="security__title">{t('account.changeEmail')}</h2>
          <EmailChangeForm />
        </section>
      </TabPanel>

      {/* ── Devices ────────────────────────────────── */}
      <TabPanel id="security" value="devices" active={tab === 'devices'}>
        <section className="security-devices">
          <h2 className="security__title">{t('account.devices')}</h2>
          <p className="muted">{t('account.devicesHint')}</p>
          <SessionList />
        </section>
      </TabPanel>
    </>
  );
}
