import { http } from '@/shared/http';

import type { StudentProfile, StudyBundle } from './types';

/**
 * حزم الطالب الحالي.
 *
 * ⚠️  الخادم يختارها من **كليته وسنته** — لا الواجهة.
 *
 *     فلترة محلية تعني تحميل كل الحزم لكل الجامعات ثم عرض حزمة
 *     واحدة، وتعني أيضًا طالبًا يرى حزم كلية ليست كليته.
 */
export const getMyBundles = () => http.get<StudyBundle[]>('/academic/me/bundles/');

export const getBundle = (slug: string) =>
  http.get<StudyBundle>(`/academic/bundles/${slug}/`);

/**
 * ⚠️  يعيد `null` بحالة `200` لغير الطلاب — لا `404`.
 *
 *     غياب الملف الأكاديمي حالة **عادية** لا خطأ: أغلب الحسابات
 *     ليست طلابية. معاملته كخطأ تُظهر رسالة عطل لمستخدم لم يخطئ.
 */
export const getMyStudentProfile = () => http.get<StudentProfile | null>('/academic/me/');
