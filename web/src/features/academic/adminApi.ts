import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * الشجرة الأكاديمية والحزم — للأدمن.
 *
 * ⚠️  **الشجرة شرط لتسجيل أي طالب.**
 *
 *     الطالب يختار جامعته وكليته قبل إنشاء حسابه. ومتجر بلا شاشة
 *     جامعات لا يستقبل طالبًا واحدًا من لوحته — تُدار البيانات من
 *     سطر الأوامر أو لا تُدار.
 *
 * ⚠️  و**القوائم بلا ترقيم** (`pagination_class = None` على الخادم).
 *
 *     الشجرة صغيرة بطبعها: جامعات بالعشرات وكليات بالمئات. توقّع
 *     `results` هنا كان يعطي `undefined` صامتًا وجدولًا فارغًا.
 */

export interface University {
  id: string;
  slug: string;
  code: string;
  name_ar: string;
  name_en: string;
  city: string;
  governorate: string;
  website: string;
  is_active: boolean;
  faculty_count: number;
}

export interface Faculty {
  id: string;
  slug: string;
  university: string;
  university_name: string;
  code: string;
  name_ar: string;
  name_en: string;
  years_count: number;
  is_active: boolean;
  department_count: number;
  student_count: number;
}

export interface Department {
  id: string;
  slug: string;
  faculty: string;
  faculty_name: string;
  code: string;
  name_ar: string;
  name_en: string;
  is_active: boolean;
}

export type BundleKind = 'REQUIRED' | 'RECOMMENDED' | 'OPTIONAL';

export interface Bundle {
  id: string;
  slug: string;
  faculty: string;
  faculty_name: string;
  department: string | null;
  academic_year: number;
  kind: BundleKind;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  display_order: number;
  is_active: boolean;
  item_count: number;
}

export interface BundleItem {
  id: string;
  bundle: string;
  product: string;
  product_sku: string;
  product_name: string;
  variant: string | null;
  quantity: number;
  is_essential: boolean;
  note_ar: string;
  note_en: string;
  display_order: number;
}

export interface StudentRow {
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

// ── القراءة ────────────────────────────────────────────────

export function useUniversities() {
  return useQuery({
    queryKey: ['academic', 'admin', 'universities'],
    queryFn: () => http.get<University[]>('/academic/admin/universities/'),
  });
}

export function useFaculties(university?: string) {
  return useQuery({
    queryKey: ['academic', 'admin', 'faculties', university ?? ''],
    queryFn: () => http.get<Faculty[]>('/academic/admin/faculties/', { params: { university } }),
  });
}

export function useDepartments(faculty?: string) {
  return useQuery({
    queryKey: ['academic', 'admin', 'departments', faculty ?? ''],
    queryFn: () => http.get<Department[]>('/academic/admin/departments/', { params: { faculty } }),
  });
}

export function useBundles(filters: { faculty?: string; academic_year?: number }) {
  return useQuery({
    queryKey: ['academic', 'admin', 'bundles', filters],
    queryFn: () => http.get<Bundle[]>('/academic/admin/bundles/', { params: { ...filters } }),
  });
}

export function useBundleItems(bundle: string | null) {
  return useQuery({
    queryKey: ['academic', 'admin', 'bundle-items', bundle],
    queryFn: () => http.get<BundleItem[]>(`/academic/admin/bundles/${bundle}/items/`),
    enabled: bundle !== null,
  });
}

export interface StudentFilters {
  university?: string;
  faculty?: string;
  academic_year?: number;
  verified?: string;
  page?: number;
}

export function useStudents(filters: StudentFilters) {
  return useQuery({
    queryKey: ['academic', 'admin', 'students', filters],
    queryFn: () =>
      http.get<PagedResponse<StudentRow>>('/academic/admin/students/', { params: { ...filters } }),
  });
}

// ── الكتابة ────────────────────────────────────────────────

/**
 * ⚠️  إبطال الشجرة كلها بعد أي كتابة.
 *
 *     حذف كلية يغيّر عدد كليات جامعتها، وإنشاء حزمة يغيّر عدّاد
 *     بنود لا شيء آخر يعرف به. إبطال الفرع وحده يترك الشاشة تعرض
 *     عدّادات من لحظة سابقة.
 */
function useAcademicMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['academic'] }),
  });
}

export function useSaveUniversity() {
  return useAcademicMutation(({ id, ...body }: Partial<University> & { id?: string }) =>
    id
      ? http.patch<University>(`/academic/admin/universities/${id}/`, body)
      : http.post<University>('/academic/admin/universities/', body),
  );
}

export function useDeleteUniversity() {
  return useAcademicMutation((id: string) =>
    http.delete<void>(`/academic/admin/universities/${id}/`),
  );
}

export function useSaveFaculty() {
  return useAcademicMutation(({ id, ...body }: Partial<Faculty> & { id?: string }) =>
    id
      ? http.patch<Faculty>(`/academic/admin/faculties/${id}/`, body)
      : http.post<Faculty>('/academic/admin/faculties/', body),
  );
}

export function useDeleteFaculty() {
  return useAcademicMutation((id: string) => http.delete<void>(`/academic/admin/faculties/${id}/`));
}

/** ⚠️  الترقية **يدوية**: العام الدراسي يبدأ في مواعيد مختلفة. */
export function usePromoteStudents() {
  return useAcademicMutation((id: string) =>
    http.post<{ faculty: string; promoted: number; note: string }>(
      `/academic/admin/faculties/${id}/promote/`,
      {},
    ),
  );
}

export function useSaveDepartment() {
  return useAcademicMutation(({ id, ...body }: Partial<Department> & { id?: string }) =>
    id
      ? http.patch<Department>(`/academic/admin/departments/${id}/`, body)
      : http.post<Department>('/academic/admin/departments/', body),
  );
}

export function useDeleteDepartment() {
  return useAcademicMutation((id: string) =>
    http.delete<void>(`/academic/admin/departments/${id}/`),
  );
}

export function useSaveBundle() {
  return useAcademicMutation(({ id, ...body }: Partial<Bundle> & { id?: string }) =>
    id
      ? http.patch<Bundle>(`/academic/admin/bundles/${id}/`, body)
      : http.post<Bundle>('/academic/admin/bundles/', body),
  );
}

export function useDeleteBundle() {
  return useAcademicMutation((id: string) => http.delete<void>(`/academic/admin/bundles/${id}/`));
}

export function useSaveBundleItem() {
  return useAcademicMutation(
    ({ bundle, id, ...body }: Partial<BundleItem> & { bundle: string; id?: string }) =>
      id
        ? http.patch<BundleItem>(`/academic/admin/bundles/${bundle}/items/${id}/`, body)
        : http.post<BundleItem>(`/academic/admin/bundles/${bundle}/items/`, body),
  );
}

export function useDeleteBundleItem() {
  return useAcademicMutation(({ bundle, id }: { bundle: string; id: string }) =>
    http.delete<void>(`/academic/admin/bundles/${bundle}/items/${id}/`),
  );
}
