import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { updateMe } from '@/features/auth/api';
import { useAuth } from '@/features/auth/useAuth';
import { useStudentVerificationEnforced } from '@/features/settings/publicConfig';
import { useTabParam } from '@/shared/hooks/useTabParam';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { TabPanel } from '@/shared/ui/TabPanel';
import { CustomerProfileCard } from '@/portals/account/components/CustomerProfileCard';

import './ProfilePage.css';

const TABS = ['account', 'customer'] as const;

/**
 * The personal profile.
 *
 * ⚠️  **The email is not editable here.**
 *
 *     Changing it goes through confirmation from both addresses
 *     (`/auth/email/change/`) — the old one so it knows its account is being
 *     moved, and the new one to prove ownership. A simple text field here means
 *     an account hijacked by editing one field.
 *
 * ⚠️  Two tabs, and **both stay mounted**.
 *
 *     "Account" is `auth/me` data and "Customer profile" is `customers/me` data —
 *     two different records with two save paths (see the card below). Unmounting
 *     the tab the user leaves would throw away what they had typed but not yet
 *     saved, so the inactive one is only hidden.
 */
export function ProfilePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [tab, setTab] = useTabParam(TABS, 'account');
  // ⚠️  The verification row exists only while verification is a requirement. With
  //     the switch off, "Verification: not verified" is a status that gates nothing,
  //     and shows every new account a problem they do not have.
  const verificationEnforced = useStudentVerificationEnforced();

  const [form, setForm] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    phone: user?.phone ?? '',
  });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  if (!user) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    setFieldErrors({});
    setPending(true);

    try {
      await updateMe(form);
      setSaved(true);
    } catch (cause) {
      if (isApiError(cause)) {
        setError(cause.displayMessage);
        setFieldErrors({ phone: cause.fieldError('phone') ?? '' });
      } else {
        setError(t('state.errorTitle'));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PageHeader title={t('account.profile')} />

      <StatusTabs
        id="profile"
        label={t('account.profileTabsLabel')}
        value={tab}
        onChange={(next) => {
          setTab(next as (typeof TABS)[number]);
        }}
        options={[
          { value: 'account', label: t('account.profileTab.account') },
          { value: 'customer', label: t('account.profileTab.customer') },
        ]}
      />

      <TabPanel
        id="profile"
        value="account"
        active={tab === 'account'}
        keepMounted
        className="profile__panel"
      >
        <section className="surface profile__identity">
          <div className="profile__row">
            <span className="muted">{t('auth.email')}</span>
            <span className="profile__email">{user.email}</span>
          </div>

          <div className="profile__row">
            <span className="muted">{t('auth.accountType')}</span>
            <span>{t(`accountType.${user.account_type}`)}</span>
          </div>

          {verificationEnforced ? (
            <div className="profile__row">
              <span className="muted">{t('account.verificationStatus')}</span>
              <Badge
                tone={
                  user.verification_status === 'VERIFIED'
                    ? 'success'
                    : user.verification_status === 'REJECTED'
                      ? 'danger'
                      : 'neutral'
                }
              >
                {t(`verification.${user.verification_status}`)}
              </Badge>
            </div>
          ) : null}
        </section>

        <form className="surface profile__form" onSubmit={(event) => void handleSubmit(event)}>
          {error ? <Alert tone="danger">{error}</Alert> : null}
          {saved ? <Alert tone="success">{t('account.saved')}</Alert> : null}

          <div className="profile__grid">
            <Field
              label={t('auth.firstName')}
              value={form.first_name}
              autoComplete="given-name"
              onChange={(event) => {
                setForm((c) => ({ ...c, first_name: event.target.value }));
              }}
            />
            <Field
              label={t('auth.lastName')}
              value={form.last_name}
              autoComplete="family-name"
              onChange={(event) => {
                setForm((c) => ({ ...c, last_name: event.target.value }));
              }}
            />
          </div>

          <Field
            label={t('auth.phone')}
            type="tel"
            value={form.phone}
            autoComplete="tel"
            error={fieldErrors.phone || undefined}
            onChange={(event) => {
              setForm((c) => ({ ...c, phone: event.target.value }));
            }}
          />

          <Button type="submit" loading={pending}>
            {t('common.save')}
          </Button>
        </form>
      </TabPanel>

      {/* ⚠️  A separate tab rather than fields in the same form: this is
          customer profile data (`customers/me`), not account data
          (`auth/me`) — and one form with two save paths produces a half
          save when one of them fails. */}
      <TabPanel
        id="profile"
        value="customer"
        active={tab === 'customer'}
        keepMounted
        className="profile__panel"
      >
        <CustomerProfileCard />
      </TabPanel>
    </>
  );
}
