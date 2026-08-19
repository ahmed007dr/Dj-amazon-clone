import { http } from '@/shared/http';

import type {
  StudentProfile,
  StudentProfilePayload,
  StudyBundle,
  University,
} from './types';

/**
 * The current student's bundles.
 *
 * ⚠️  The server selects them from **their faculty and year** — not the frontend.
 *
 *     Filtering locally means downloading every bundle for every university and
 *     then displaying one, and it also means a student seeing bundles from a
 *     faculty that is not theirs.
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
