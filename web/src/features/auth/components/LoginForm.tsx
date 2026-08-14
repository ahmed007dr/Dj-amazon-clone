import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import { useAuth } from '../useAuth';

import './LoginForm.css';

/**
 * نموذج تسجيل الدخول.
 *
 * ⚠️  رسالة فشل الدخول **لا تفرّق** بين بريد غير موجود وكلمة مرور
 *     خاطئة.
 *
 *     التفريق يحوّل الشاشة إلى أداة تعداد حسابات: يجرّب المهاجم
 *     بريدًا ويعرف من الرسالة وحدها إن كان مسجَّلًا. الخادم يوحّد
 *     الرسالة، والواجهة لا تُعيد بناء الفرق من رموز الخطأ.
 */
export function LoginForm({ onSuccess }: { onSuccess?: () => void }) {
  const { t } = useTranslation();
  const { signIn } = useAuth();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);

    try {
      await signIn({ identifier, password });
      onSuccess?.();
    } catch (cause) {
      if (!isApiError(cause)) {
        setError(t('state.errorTitle'));
        return;
      }

      if (cause.isOffline) {
        setError(t('state.offlineBody'));
      } else if (cause.isRateLimited) {
        // ⚠️  رسالة مختلفة عن فشل الدخول: المستخدم لم يخطئ البيانات
        //     بل تجاوز الحد، والتصرّف المطلوب هو الانتظار لا التصحيح.
        setError(cause.displayMessage);
      } else {
        setError(cause.displayMessage || t('auth.loginFailed'));
        setFieldErrors({
          identifier: cause.fieldError('identifier') ?? '',
          password: cause.fieldError('password') ?? '',
        });
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="login-form" onSubmit={(event) => void handleSubmit(event)} noValidate>
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <Field
        label={t('auth.identifier')}
        // ⚠️  `text` لا `email` — الحقل يقبل رقم هاتف أيضًا، و`email`
        //     يجعل المتصفح يرفض «01001234567» بتحقق لا يخصّه
        type="text"
        inputMode="email"
        name="identifier"
        value={identifier}
        // يخبر مدير كلمات المرور بما يملأ — بدونه يملأ الحقل الخطأ
        autoComplete="username"
        required
        hint={t('auth.identifierHint')}
        error={fieldErrors.identifier || undefined}
        onChange={(event) => {
          setIdentifier(event.target.value);
        }}
      />

      <Field
        label={t('auth.password')}
        type="password"
        name="password"
        value={password}
        autoComplete="current-password"
        required
        error={fieldErrors.password || undefined}
        onChange={(event) => {
          setPassword(event.target.value);
        }}
      />

      <Button type="submit" block loading={pending}>
        {t('auth.signIn')}
      </Button>
    </form>
  );
}
