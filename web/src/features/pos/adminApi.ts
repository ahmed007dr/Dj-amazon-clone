import { useQuery } from '@tanstack/react-query';

import { http } from '@/shared/http';
import type { PagedResponse } from '@/features/orders/adminApi';

import type { Register, Session } from './api';

/**
 * ورديات نقطة البيع — من بوابة الأدمن.
 *
 * ⚠️  **الأدمن يرى `expected_cash` و`variance` دائمًا؛ الكاشير لا.**
 *
 *     الفارق ليس تشدّدًا في الصلاحيات بل جوهر التسوية: عرض
 *     المتوقَّع للكاشير قبل أن يعدّ يجعله يعدّ حتى يطابقه، فيصير
 *     الفرق صفرًا دائمًا ولا تكشف التسوية شيئًا. الأدمن يقرأ بعد
 *     وقوع العدّ، فلا يفسده.
 */

export interface AdminSessionFilters {
  register?: string;
  status?: string;
  page?: number;
}

export const listAdminSessions = (params: AdminSessionFilters) =>
  // ⚠️  `{ ...params }` لا `params`: الواجهة المصرَّحة الحقول بلا
  //     توقيع فهرسة، فلا تُقبل مباشرةً كخريطة استعلام.
  http.get<PagedResponse<Session>>('/pos/admin/sessions/', { params: { ...params } });

export const listAdminRegisters = () => http.get<Register[]>('/pos/admin/registers/');

export function useAdminSessions(filters: AdminSessionFilters) {
  return useQuery({
    queryKey: ['admin', 'pos-sessions', filters],
    queryFn: () => listAdminSessions(filters),
  });
}

export function useAdminRegisters() {
  return useQuery({
    queryKey: ['admin', 'pos-registers'],
    queryFn: listAdminRegisters,
  });
}
