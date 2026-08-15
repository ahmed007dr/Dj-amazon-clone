import { Outlet } from 'react-router-dom';

import { useMyEmployeeProfile } from '@/features/employees/api';
import { isApiError } from '@/shared/http/errors';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useTranslation } from 'react-i18next';

import { StaffHeader } from './components/StaffHeader';

import './StaffShell.css';

/**
 * قشرة بوابة الموظفين.
 *
 * ⚠️  **الملف شرط دخول لا خطوة داخل الشاشة.**
 *
 *     كل نقطة على الخادم ترفض العمل بلا ملف موظف نشط. ترك
 *     الشاشات تُفتح ثم تفشل واحدة واحدة يعطي المستخدم أربع رسائل
 *     خطأ متفرّقة بدل جواب واحد.
 *
 * ⚠️  و**الموظف الموقوف يُصدّ هنا** لا عند أول عملية.
 *
 *     موظف انتهت خدمته وتوكنه صالح هو أوضح ثغرة ممكنة؛ والخادم
 *     يردّ ٤٠٣ على كل نقطة، والقشرة تترجمها إلى رسالة مفهومة.
 */
export function StaffShell() {
  const { t } = useTranslation();
  const profile = useMyEmployeeProfile();

  if (profile.isPending) return <Spinner />;

  if (profile.error) {
    const forbidden = isApiError(profile.error) && profile.error.status === 403;

    return (
      <div className="staff-shell">
        <StaffHeader />
        <main className="staff-shell__body">
          <StateMessage
            icon="🔒"
            title={forbidden ? t('staff.noAccess') : t('staff.noProfile')}
            body={
              isApiError(profile.error)
                ? profile.error.displayMessage
                : t('state.errorTitle')
            }
          />
        </main>
      </div>
    );
  }

  return (
    <div className="staff-shell">
      <StaffHeader />
      <main className="staff-shell__body">
        <Outlet />
      </main>
    </div>
  );
}
