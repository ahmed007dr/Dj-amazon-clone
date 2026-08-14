import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { updateMe } from '@/features/auth/api';
import { useAuth } from '@/features/auth/useAuth';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import './ProfilePage.css';

/**
 * الملف الشخصي.
 *
 * ⚠️  **البريد غير قابل للتعديل هنا.**
 *
 *     تغييره يمرّ بتأكيد من العنوانين معًا (`/auth/email/change/`)
 *     — القديم ليعرف أن حسابه يُنقل، والجديد ليثبت ملكيته. حقل
 *     نصي بسيط هنا يعني اختطاف حساب بتعديل حقل واحد.
 */
export function ProfilePage() {
  const { t } = useTranslation();
  const { user } = useAuth();

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

      <section className="surface profile__identity">
        <div className="profile__row">
          <span className="muted">{t('auth.email')}</span>
          <span className="profile__email">{user.email}</span>
        </div>

        <div className="profile__row">
          <span className="muted">{t('auth.accountType')}</span>
          <span>{t(`accountType.${user.account_type}`)}</span>
        </div>

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
    </>
  );
}
