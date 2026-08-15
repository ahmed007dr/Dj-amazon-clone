/** عقود النطاق الأكاديمي — تطابق `academic/serializers.py`. */

export type BundleKind = 'REQUIRED' | 'RECOMMENDED' | 'OPTIONAL';

/**
 * ⚠️  **بلا سعر.**
 *
 *     السعر يحسبه `pricing` لكل عميل حسب قائمته — وإدراجه في
 *     الحزمة يعني رقمًا يتقادم بصمت. الطالب يرى السعر عند إضافة
 *     الحزمة للسلة، محسوبًا بقائمة الطلاب.
 */
export interface BundleItem {
  id: string;
  product: string;
  product_slug: string;
  product_sku: string;
  product_name_ar: string;
  product_name_en: string;
  variant: string | null;
  quantity: number;
  /** الأساسي مطلوب؛ وغيره يمكن حذفه من السلة بعد الإضافة. */
  is_essential: boolean;
  note_ar: string;
  note_en: string;
}

export interface StudyBundle {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  kind: BundleKind;
  academic_year: number;
  image: string | null;
  items: BundleItem[];
  item_count: number;
}

export interface StudentProfile {
  id: string;
  university: string;
  university_name: string;
  faculty: string;
  faculty_name: string;
  department: string | null;
  department_name: string | null;
  academic_year: number;
  student_number: string;
  is_verified: boolean;
  expected_graduation_year: number | null;
}

export interface Department {
  id: string;
  code: string;
  slug: string;
  name_ar: string;
  name_en: string;
}

export interface Faculty {
  id: string;
  code: string;
  slug: string;
  name_ar: string;
  name_en: string;
  /** عدد سنوات الدراسة — يحدّ خيارات السنة الدراسية. */
  years_count: number;
  departments: Department[];
}

/**
 * الجامعة بكلياتها وأقسامها في استجابة واحدة.
 *
 * ⚠️  الشجرة كاملة عمدًا (`UniversitySerializer`) — نموذج الملف
 *     الأكاديمي يحتاجها كلها دفعةً، والتحميل التدريجي يعني ثلاثة
 *     نداءات متتابعة يرى الطالب بينها قوائم فارغة.
 */
export interface University {
  id: string;
  code: string;
  slug: string;
  name_ar: string;
  name_en: string;
  city: string;
  logo: string | null;
  faculties: Faculty[];
}

/**
 * حمولة إنشاء الملف الأكاديمي.
 *
 * ⚠️  `department` اختياري: كليات كثيرة بلا أقسام في السنوات
 *     الأولى، وإلزامه يمنع طالب السنة الأولى من إكمال ملفه.
 */
export interface StudentProfilePayload {
  university: string;
  faculty: string;
  department?: string | null;
  academic_year: number;
  student_number?: string;
}
