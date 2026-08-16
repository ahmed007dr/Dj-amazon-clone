import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { requestEmailChange } from '@/features/auth/api';
import { useAuth } from '@/features/auth/useAuth';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

/**
 * طلب تغيير البريد.
 *
 * ⚠️  **خطوتان لا واحدة**: طلب هنا، ثم تأكيد برابط يصل **العنوان
 *     الجديد**. الخطوة الواحدة تسمح بتحويل الحساب إلى بريد لا
 *     يملكه صاحبه — وهي أسرع طريق لسرقة حساب من جلسة مفتوحة.
 *
 * ⚠️  و**كلمة المرور مطلوبة** لنفس السبب: جهاز مفتوح بلا صاحبه
 *     يكفي لتغيير البريد ثم الاستيلاء عبر «نسيت كلمة المرور».
 */
export function EmailChangeForm() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);

  const request = useMutation({
    mutationFn: () => requestEmailChange(email, password),
    onSuccess: () => {
      setSent(true);
      setEmail('');
      setPassword('');
      setFieldErrors({});
    },
    onError: (error) => {
      if (isApiError(error)) {
        const next: Record<string, string> = {};
        for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
        setFieldErrors(next);
      }
    },
  });

  if (sent) {
    // ⚠️  الرسالة تسمّي **العنوان الجديد** لا القديم: المستخدم قد
    //     يكون أخطأ في كتابته، وذكره هو ما يجعله يلاحظ.
    return <Alert tone="success">{t('account.emailChangeSent')}</Alert>;
  }

  return (
    <>
      <p className="muted">{t('account.currentEmail', { email: user?.email ?? '' })}</p>

      <Field
        label={t('account.newEmail')}
        type="email"
        dir="ltr"
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        {...(fieldErrors.new_email ? { error: fieldErrors.new_email } : {})}
      />

      <Field
        label={t('auth.currentPassword')}
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        hint={t('account.emailChangeWhyPassword')}
        {...(fieldErrors.current_password ? { error: fieldErrors.current_password } : {})}
      />

      <Button
        loading={request.isPending}
        disabled={!email || !password}
        onClick={() => request.mutate()}
      >
        {t('account.sendEmailChange')}
      </Button>
    </>
  );
}
