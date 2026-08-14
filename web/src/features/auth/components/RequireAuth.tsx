import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router-dom';

import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { useAuth } from '../useAuth';

/**
 * حارس المسار.
 *
 * ⚠️  **ليس أمانًا.** الخادم يرفض بصرف النظر عن هذا المكوّن.
 *
 *     فائدته أن المستخدم يرى شاشة دخول بدل شاشة مليئة برسائل ٤٠٣.
 *
 * ⚠️  ينتظر انتهاء استعادة الجلسة قبل أن يحكم.
 *
 *     بدون ذلك يُطرد كل مستخدم عائد إلى صفحة الدخول في اللحظة التي
 *     يُقلع فيها التطبيق — لأن `user` لم يصل بعد وإن كانت جلسته
 *     صالحة تمامًا.
 */
export function RequireAuth({
  children,
  allow,
}: {
  children: ReactNode;
  /** فحص إضافي على الحساب — أدمن مثلًا. */
  allow?: (user: NonNullable<ReturnType<typeof useAuth>['user']>) => boolean;
}) {
  const { t } = useTranslation();
  const { user, isRestoring } = useAuth();
  const location = useLocation();

  if (isRestoring) return <Spinner />;

  if (!user) {
    // ⚠️  الوجهة تُحفَظ ليعود إليها بعد الدخول بدل أن يبدأ من الرئيسية
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (allow && !allow(user)) {
    return <StateMessage icon="⚿" title={t('state.forbiddenTitle')} />;
  }

  return children;
}
