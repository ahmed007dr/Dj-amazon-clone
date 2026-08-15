import { http } from '@/shared/http';

import type {
  StudentProfile,
  StudentProfilePayload,
  StudyBundle,
  University,
} from './types';

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

/**
 * شجرة الجامعات — **عامة بلا توكن**.
 *
 * ⚠️  الخادم يفتحها لغير المسجَّل عمدًا: الطالب يختار جامعته قبل
 *     أن يملك حسابًا. ولذلك لا تُقيَّد هنا بـ `enabled` على الجلسة.
 */
export const getUniversities = () => http.get<University[]>('/academic/universities/');

export const createStudentProfile = (payload: StudentProfilePayload) =>
  http.post<StudentProfile>('/academic/me/', payload);

/**
 * ⚠️  `PATCH` جزئي: الطالب يرقّي سنته أو يصحّح قسمه دون إعادة
 *     إرسال الشجرة كلها — وإرسال حقل لم يتغيّر يُعيد فحص الاتساق
 *     على قيمة قديمة فيرفضها الخادم بلا سبب مفهوم للطالب.
 */
export const updateStudentProfile = (payload: Partial<StudentProfilePayload>) =>
  http.patch<StudentProfile>('/academic/me/', payload);
