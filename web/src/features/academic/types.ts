/** Academic domain contracts — matching `academic/serializers.py`. */

export type BundleKind = 'REQUIRED' | 'RECOMMENDED' | 'OPTIONAL';

/**
 * ⚠️  **No price.**
 *
 *     `pricing` computes the price per customer from their list — and including
 *     it in the bundle means a number going silently stale. The student sees
 *     the price when adding the bundle to the cart, computed against the
 *     student price list.
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
  /** The essential item is required; the rest can be removed from the cart after adding. */
  is_essential: boolean;
  note_ar: string;
  note_en: string;
}

/**
 * A bundle as the **list** returns it — a card, not a page.
 *
 * ⚠️  No `items`: the list carries `item_count` only, and the full item list
 *     comes with the detail (`StudyBundle`). Typing the card with `StudyBundle`
 *     would promise an array the list endpoint never sends.
 *
 * ⚠️  And it says **whose** bundle it is. Bundles are public and unfiltered by
 *     the visitor's own profile, so "Year 2 essentials" is meaningless without
 *     the faculty and university beside it.
 */
export interface BundleSummary {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  kind: BundleKind;
  academic_year: number;
  image: string | null;
  item_count: number;
  faculty: string;
  faculty_name_ar: string;
  faculty_name_en: string;
  university: string;
  university_name_ar: string;
  university_name_en: string;
  /** `null` = a faculty-wide bundle, for every department. */
  department: string | null;
  department_name_ar: string | null;
  department_name_en: string | null;
}

export interface StudyBundle extends BundleSummary {
  items: BundleItem[];
}

/**
 * What a visitor may narrow the public bundles list by — all optional, and
 * **nothing is applied by default**.
 */
export interface BundleFilters {
  university?: string;
  faculty?: string;
  academic_year?: number;
  kind?: BundleKind;
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
  /** The number of study years — it bounds the study-year options. */
  years_count: number;
  departments: Department[];
}

/**
 * A university with its faculties and departments in one response.
 *
 * ⚠️  The full tree deliberately (`UniversitySerializer`) — the academic profile
 *     form needs all of it at once, and lazy loading means three consecutive
 *     calls with the student staring at empty lists in between.
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
 * The payload for creating the academic profile.
 *
 * ⚠️  `department` is optional: many faculties have no departments in the early
 *     years, and requiring it stops a first-year student completing their profile.
 */
export interface StudentProfilePayload {
  university: string;
  faculty: string;
  department?: string | null;
  academic_year: number;
  student_number?: string;
}
