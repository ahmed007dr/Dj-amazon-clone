import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';
import type { PagedResponse } from '@/features/orders/adminApi';

import type { Register, Session } from './api';

/**
 * Point-of-sale shifts — from the admin portal.
 *
 * ⚠️  **The admin always sees `expected_cash` and `variance`; the cashier does not.**
 *
 *     The difference is not permissions strictness but the essence of the
 *     reconciliation: showing the expected figure to the cashier before they
 *     count makes them count until it matches, so the discrepancy is always
 *     zero and the reconciliation reveals nothing. The admin reads after the
 *     count has happened, so they do not corrupt it.
 */

export interface AdminSessionFilters {
  register?: string;
  status?: string;
  page?: number;
}

export const listAdminSessions = (params: AdminSessionFilters) =>
  // ⚠️  `{ ...params }`, not `params`: the explicitly typed interface has no
  //     index signature, so it is not accepted directly as a query map.
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

/**
 * A single shift in detail.
 *
 * ⚠️  **The list is condensed and the detail is requested.**
 *
 *     The shift's row in the table shows the discrepancy and not its
 *     composition: how many sales in cash, how many by card, and how much left
 *     the drawer and why. Fetching that for every row means dozens of calls for
 *     a page from which one shift gets read.
 */
export function useAdminSession(id: string | null) {
  return useQuery({
    queryKey: ['admin', 'pos-session', id],
    queryFn: () => http.get<Session>(`/pos/admin/sessions/${id}/`),
    enabled: id !== null,
  });
}

/**
 * Managing registers.
 *
 * ⚠️  **A register is disabled and never deleted** — and the server exposes no
 *     `DELETE` at all: every shift and every sale points at it, and deleting it
 *     severs the branch's history from its source.
 *
 * ⚠️  And the server answers 409 to disabling or moving it while a shift is open
 *     on it; the screen shows its message as it is rather than inventing an explanation.
 */
export function useSaveRegister() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Register> & { id?: string }) =>
      id
        ? http.patch<Register>(`/pos/admin/registers/${id}/`, body)
        : http.post<Register>('/pos/admin/registers/', body),
    onSuccess: () => {
      // ⚠️  Invalidate the cashier portal along with it: a disabled register must
      //     disappear from the open-shift list immediately, not after a reload.
      void queryClient.invalidateQueries({ queryKey: ['admin', 'pos-registers'] });
      void queryClient.invalidateQueries({ queryKey: ['pos', 'registers'] });
    },
  });
}
