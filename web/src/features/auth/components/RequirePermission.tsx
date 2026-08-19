import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useCan } from '@/features/auth/useCan';
import { StateMessage } from '@/shared/ui/StateMessage';

/**
 * حارس شاشة بصلاحية.
 *
 * ⚠️  **الرابط يختفي والشاشة تشرح — لا تختفي هي أيضًا.**
 *
 *     من يصل بالمسار المباشر (رابط محفوظ · مُشارَك من زميل) يجب
 *     أن يقرأ «هذه الشاشة تحتاج صلاحية» لا «الصفحة غير موجودة».
 *     الثانية تجعله يبلّغ عن رابط مكسور، والأولى تجعله يطلب
 *     الصلاحية من مديره — وهو ما نريده بالضبط.
 *
 * ⚠️  و**الرسالة تسمّي الشاشة**: «تحتاج صلاحية» بلا اسم لا تُنقَل
 *     إلى من يمنح.
 */
export function RequirePermission({
  permission,
  screen,
  children,
}: {
  permission: string;
  /** مفتاح ترجمة اسم الشاشة — يُذكر في الرسالة ليُطلَب بالاسم. */
  screen?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const can = useCan();

  if (!can(permission)) {
    return (
      <StateMessage
        icon="🔒"
        title={t('state.forbiddenTitle')}
        body={
          screen
            ? t('state.forbiddenScreen', { screen: t(screen) })
            : t('state.forbiddenBody')
        }
      />
    );
  }

  return children;
}
