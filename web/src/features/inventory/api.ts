import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * ⚠️  `available` is **computed, not stored**: physical minus reserved, damaged
 *     and expired. And it is the only number that matters when selling.
 */
export interface Stock {
  id: number;
  product: string;
  product_sku: string;
  product_name: string;
  variant: string | null;
  location: string;
  location_code: string;
  quantity_physical: number;
  quantity_reserved: number;
  quantity_damaged: number;
  quantity_expired: number;
  available: number;
  reorder_point: number;
  critical_point: number;
  needs_reorder: boolean;
  is_critical: boolean;
  last_counted_at: string | null;
}

export type AlertType =
  | 'LOW_STOCK'
  | 'CRITICAL_STOCK'
  | 'OUT_OF_STOCK'
  | 'EXPIRING_SOON'
  | 'EXPIRED';

export interface StockAlert {
  id: string;
  alert_type: AlertType;
  product: string;
  product_sku: string;
  product_name: string;
  location: string;
  location_code: string;
  batch: string | null;
  current_value: number;
  threshold_value: number;
  is_resolved: boolean;
  created_at: string;
}

export interface StockLocation {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  kind: string;
  is_default: boolean;
  is_sellable: boolean;
  is_active: boolean;
}

export const listStock = (params: {
  location?: string;
  status?: string;
  search?: string;
  page?: number;
}) => http.get<PagedResponse<Stock>>('/inventory/stock/', { params: { ...params } });

export const listAlerts = (params: { type?: string; resolved?: string; page?: number }) =>
  http.get<PagedResponse<StockAlert>>('/inventory/alerts/', { params: { ...params } });

export const listLocations = () => http.get<StockLocation[]>('/inventory/locations/');

/**
 * Stock locations — consumed by more than one screen.
 *
 * ⚠️  A deliberately long `staleTime`: locations are infrastructure that changes
 *     once every few months, and refetching them every time a purchasing panel
 *     opens is a call with no benefit.
 */
export function useInventoryLocations() {
  return useQuery({
    queryKey: ['inventory', 'locations'],
    queryFn: listLocations,
    staleTime: 30 * 60 * 1000,
  });
}

/**
 * ⚠️  Maintenance runs the periodic jobs by hand: releasing expired reservations ·
 *     quarantining expired batches · checking the alerts.
 *
 *     Having a button for it is not a substitute for scheduling — it is what
 *     lets the admin run it immediately when they doubt a figure, rather than
 *     waiting for the next cycle.
 */
export const runMaintenance = () =>
  http.post<Record<string, number>>('/inventory/maintenance/');

// ═══════════════════════════════════════════════════════════
//  The movement log
// ═══════════════════════════════════════════════════════════

/**
 * ⚠️  It matches `MovementType` on the server literally.
 *
 *     Every change in stock leaves a movement without exception — and the log
 *     is what answers "where did the fifty boxes go?".
 */
export type MovementType =
  | 'RECEIPT'
  | 'SALE'
  | 'RETURN_IN'
  | 'RETURN_OUT'
  | 'TRANSFER_OUT'
  | 'TRANSFER_IN'
  | 'ADJUSTMENT_UP'
  | 'ADJUSTMENT_DOWN'
  | 'DAMAGE'
  | 'EXPIRY'
  | 'COUNT'
  | 'RESERVE'
  | 'RELEASE';

export interface StockMovement {
  id: number;
  reference: string;
  product: string;
  product_sku: string;
  variant: string | null;
  location: string;
  location_code: string;
  batch: string | null;
  movement_type: MovementType;
  /** Positive for inbound and negative for outbound — the sign is part of the meaning */
  quantity: number;
  balance_after: number;
  unit_cost: string | null;
  reference_type: string;
  reference_id: string;
  note: string;
  performed_by: string | null;
  performed_by_email: string | null;
  created_at: string;
}

export const listMovements = (params: {
  product?: string;
  location?: string;
  type?: string;
  page?: number;
}) => http.get<PagedResponse<StockMovement>>('/inventory/movements/', { params: { ...params } });

// ═══════════════════════════════════════════════════════════
//  Commands
// ═══════════════════════════════════════════════════════════

export interface ReceiveBody {
  product: string;
  location?: string | null;
  quantity: number;
  unit_cost: string;
  expires_at?: string | null;
  supplier_batch_number?: string;
}

export interface AdjustBody {
  product: string;
  location?: string | null;
  /** Positive for an increase · negative for a decrease — and zero is refused */
  quantity: number;
  reason: string;
}

export interface TransferBody {
  product: string;
  from_location: string;
  to_location: string;
  quantity: number;
}

export interface DamageBody {
  product: string;
  location?: string | null;
  quantity: number;
  reason: string;
}

/**
 * ⚠️  Invalidate **the whole inventory tree** after any movement.
 *
 *     Receiving changes the balance, the batches and the movements, and may
 *     resolve an open alert. Invalidating one list leaves the screen showing an
 *     "out of stock" alert beside the quantity just received.
 *
 * ⚠️  **And the catalogue with it — the listing itself now depends on stock.**
 *
 *     A product whose available quantity is zero is not in the storefront list
 *     at all, so receiving a shipment does not merely change a number on a card:
 *     it puts the card back. Invalidating `inventory` alone left the catalogue
 *     serving its two-minute cache, so the person who had just received the
 *     goods opened the shop, did not find them, and had no way to tell whether
 *     the receipt had failed or the page was stale.
 *
 *     Two minutes is the right staleness for a name and a price. It is the
 *     wrong staleness for "does this exist?", and this is the moment we know the
 *     answer changed.
 */
function useInventoryMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['inventory'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
  });
}

export function useReceiveStock() {
  return useInventoryMutation((body: ReceiveBody) => http.post('/inventory/receive/', body));
}

export function useAdjustStock() {
  return useInventoryMutation((body: AdjustBody) => http.post('/inventory/adjust/', body));
}

export function useTransferStock() {
  return useInventoryMutation((body: TransferBody) => http.post('/inventory/transfer/', body));
}

export function useMarkDamaged() {
  return useInventoryMutation((body: DamageBody) => http.post('/inventory/damage/', body));
}

// ═══════════════════════════════════════════════════════════
//  Batches
// ═══════════════════════════════════════════════════════════

export interface Batch {
  id: string;
  number: string;
  product: string;
  product_sku: string;
  variant: string | null;
  location: string;
  location_code: string;
  supplier_batch_number: string;
  quantity_received: number;
  quantity_remaining: number;
  unit_cost: string;
  manufactured_at: string | null;
  expires_at: string | null;
  received_at: string;
  is_quarantined: boolean;
  is_expired: boolean;
  days_to_expiry: number | null;
}

/**
 * ⚠️  `status=expired` **includes what has expired and is still in the warehouse**.
 *
 *     And that is the more dangerous case: goods that might be sold. The screen
 *     highlights it rather than mixing it in with what is "approaching".
 */
export function useBatches(params: {
  product?: string;
  location?: string;
  status?: string;
  page?: number;
}) {
  return useQuery({
    queryKey: ['inventory', 'batches', params],
    queryFn: () =>
      http.get<PagedResponse<Batch>>('/inventory/batches/', { params: { ...params } }),
  });
}

export function useMovements(params: {
  product?: string;
  location?: string;
  type?: string;
  page?: number;
}) {
  return useQuery({
    queryKey: ['inventory', 'movements', params],
    queryFn: () => listMovements(params),
  });
}

// ═══════════════════════════════════════════════════════════
//  Stock counting
// ═══════════════════════════════════════════════════════════

export type CountStatus = 'DRAFT' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';

export interface StockCountLine {
  id: number;
  product: string;
  product_sku: string;
  product_name_ar: string;
  product_name_en: string;
  variant: string | null;
  variant_name: string | null;
  expected_quantity: number;
  counted_quantity: number;
  /** ⚠️  Computed on the server — positive is a surplus and negative a shortfall. */
  variance: number;
  note: string;
}

export interface StockCount {
  id: string;
  reference: string;
  location: string;
  location_code: string;
  status: CountStatus;
  started_at: string | null;
  completed_at: string | null;
  note: string;
  line_count: number;
  variance_count: number;
}

export interface StockCountDetail extends StockCount {
  lines: StockCountLine[];
}

export function useStockCounts(params: { location?: string; status?: string; page?: number }) {
  return useQuery({
    queryKey: ['inventory', 'counts', params],
    queryFn: () =>
      http.get<PagedResponse<StockCount>>('/inventory/counts/', { params: { ...params } }),
  });
}

export function useStockCount(id: string | null) {
  return useQuery({
    queryKey: ['inventory', 'count', id],
    queryFn: () => http.get<StockCountDetail>(`/inventory/counts/${id}/`),
    enabled: id !== null,
  });
}

export function useOpenCount() {
  return useInventoryMutation((body: { location: string; note?: string }) =>
    http.post<StockCountDetail>('/inventory/counts/open/', body),
  );
}

export function useRecordCounted() {
  return useInventoryMutation(
    ({
      count,
      line,
      counted_quantity,
      note,
    }: {
      count: string;
      line: number;
      counted_quantity: number;
      note?: string;
    }) =>
      http.post<StockCountLine>(`/inventory/counts/${count}/record/`, {
        line,
        counted_quantity,
        note,
      }),
  );
}

export function useApplyCount() {
  return useInventoryMutation((id: string) =>
    http.post<{ adjusted: number; surplus: number; shortage: number }>(
      `/inventory/counts/${id}/apply/`,
      {},
    ),
  );
}

export function useCancelCount() {
  return useInventoryMutation(({ id, reason }: { id: string; reason: string }) =>
    http.post<StockCount>(`/inventory/counts/${id}/cancel/`, { reason }),
  );
}

// ═══════════════════════════════════════════════════════════
//  Reservations and alert thresholds
// ═══════════════════════════════════════════════════════════

export interface StockReservation {
  id: string;
  product: string;
  product_sku: string;
  variant: string | null;
  location: string;
  quantity: number;
  status: 'ACTIVE' | 'RELEASED' | 'CONSUMED' | 'EXPIRED';
  reference_type: string;
  reference_id: string;
  expires_at: string | null;
  resolved_at: string | null;
}

/**
 * The current reservations.
 *
 * ⚠️  **A reservation is deducted from available and appeared on no screen at all.**
 *
 *     "The balance is 100 and available is 60 — where are the forty?" is a
 *     question with no answer without this list. The answer is always open
 *     carts or unshipped orders, and without seeing them the system looks as
 *     though it is hiding goods.
 */
export function useReservations(params: { status?: string; page?: number }, enabled = true) {
  return useQuery({
    queryKey: ['inventory', 'reservations', params],
    queryFn: () =>
      http.get<PagedResponse<StockReservation>>('/inventory/reservations/', {
        params: { ...params },
      }),
    enabled,
  });
}

/**
 * Editing the alert thresholds — **the thresholds alone**.
 *
 * ⚠️  Quantities are not edited from here (the server marks them `read_only`):
 *     every stock movement goes through its recorded path (receipt · adjustment ·
 *     transfer · damage), and editing a number directly leaves a discrepancy
 *     with no cause in the ledger.
 */
export function useUpdateStockThresholds() {
  return useInventoryMutation(
    ({ id, ...body }: { id: number; reorder_point?: number; critical_point?: number }) =>
      http.patch<Stock>(`/inventory/stock/${id}/`, body),
  );
}
