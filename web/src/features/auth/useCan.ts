import { useCallback } from 'react';

import { useAuth } from './useAuth';

/**
 * «هل يملك المستخدم هذا؟»
 *
 * ⚠️  **للعرض لا للحراسة.**
 *
 *     الخادم يرفض بصرف النظر عمّا تُظهره الشاشة. إخفاء زرّ ليس
 *     أمانًا — لكن إظهار زرّ يفشل عند الضغط تجربة سيئة، وإظهار
 *     خمسة عشر رابطًا لا يملكها المستخدم يجعله يظن النظام معطّلًا.
 *
 * ⚠️  و**المالك يملك كل شيء دائمًا**.
 *
 *     `is_owner` تُغني عن قائمة صلاحياته. وبدون هذا الاستثناء
 *     يُقفَل النظام على صاحبه عند أول ضبط خاطئ.
 *
 * ⚠️  والغياب يعني **لا** لا «ربما».
 *
 *     قبل وصول `/auth/me` تكون القائمة فارغة؛ إظهار كل شيء حتى
 *     تصل يجعل الروابط ترتجف عند كل إقلاع.
 */
export function useCan(): (permission?: string | null) => boolean {
  const { user } = useAuth();

  return useCallback(
    (permission) => {
      if (user === null) return false;
      if (user.is_owner) return true;

      // ⚠️  `null` = بلا شرط: شاشة يفتحها كل من وصل إليها.
      if (permission === undefined || permission === null) return true;

      return (user.permissions ?? []).includes(permission);
    },
    [user],
  );
}

/**
 * الشروط البنيوية — ليست صلاحيات Django.
 *
 * ⚠️  بعض البوابات على الخادم تسأل «هل له ملف؟» لا «هل يملك؟»:
 *     نقطة البيع تسأل عن نوع الحساب، وبوابة الموظفين عن ملف
 *     موظف نشط. خلطها بالصلاحيات كان يجعل الإخفاء يخالف الخادم
 *     في الاتجاهين معًا.
 */
export function useIs(): (requirement: 'owner' | 'admin' | 'employee') => boolean {
  const { user } = useAuth();

  return useCallback(
    (requirement) => {
      if (user === null) return false;

      switch (requirement) {
        case 'owner':
          return user.is_owner;
        case 'admin':
          return user.has_admin_profile || user.is_owner;
        case 'employee':
          return user.has_employee_profile || user.is_owner;
        default:
          return false;
      }
    },
    [user],
  );
}
