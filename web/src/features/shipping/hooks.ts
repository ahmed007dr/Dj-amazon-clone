import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type { AdminShipmentQuery, ShipmentStatus } from './api';

const ADMIN_KEY = ['admin', 'shipments'] as const;
const METHODS_KEY = ['shipping', 'methods'] as const;

/**
 * ⚠️  Delivery options change rarely and are read on every checkout — a long
 *     stale time here removes a request from the slowest moment in the flow.
 */
export function useShippingMethods() {
  return useQuery({
    queryKey: METHODS_KEY,
    queryFn: api.listShippingMethods,
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * Tracking by number.
 *
 * ⚠️  `enabled` guards the empty box: without it the query fires on every
 *     keystroke of an unfinished number and answers 404 to each one, so the
 *     screen shows "not found" while the customer is still typing.
 */
export function useTrackShipment(number: string) {
  return useQuery({
    queryKey: ['shipping', 'track', number],
    queryFn: () => api.trackShipment(number),
    enabled: number.trim().length > 0,
    retry: false,
  });
}

/**
 * ⚠️  A short stale time: this is an operational screen watched while couriers
 *     move, not a report read once.
 */
export function useAdminShipments(query: AdminShipmentQuery) {
  return useQuery({
    queryKey: [...ADMIN_KEY, query],
    queryFn: () => api.listAdminShipments(query),
    staleTime: 15 * 1000,
  });
}

export function useTransitionShipment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (args: {
      id: string;
      status: ShipmentStatus;
      note?: string;
      location?: string;
      tracking_number?: string;
    }) => {
      const { id, ...body } = args;
      return api.transitionShipment(id, body);
    },
    // ⚠️  The whole list is invalidated, not the one row.
    //
    //     A transition moves the shipment between status tabs and changes their
    //     counts — patching the row in place leaves it sitting under a tab it no
    //     longer belongs to, which reads as the change having failed.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ADMIN_KEY });
      void queryClient.invalidateQueries({ queryKey: ['shipping', 'track'] });
    },
  });
}

// ── Configuration ──────────────────────────────────────────

const CONFIG_KEY = ['admin', 'shipping-config'] as const;

/**
 * ⚠️  Every configuration write invalidates **the customer's side too**.
 *
 *     Raising Upper Egypt's fee changes what the next checkout quotes. Without
 *     `['shipping', 'quotes']` and `['shipping', 'methods']` here — the latter
 *     cached for ten minutes — the admin sees the new fee in the panel while
 *     the store keeps quoting the old one, and concludes the save did nothing.
 */
function useShippingConfigMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONFIG_KEY });
      void queryClient.invalidateQueries({ queryKey: METHODS_KEY });
      void queryClient.invalidateQueries({ queryKey: ['shipping', 'quotes'] });
    },
  });
}

/**
 * Which governorates have a zone, and which fall through to the default.
 *
 * ⚠️  Read by the zone form as its **picker**, not as a report.
 *
 *     `for_governorate` matches the name literally, so a typed "الاسكندرية"
 *     against a stored "الإسكندرية" quotes the default fee for Alexandria with
 *     nothing anywhere reporting a problem. A picker fed from the server cannot
 *     produce that; a text box eventually will.
 */
export function useShippingCoverage(enabled = true) {
  return useQuery({
    queryKey: [...CONFIG_KEY, 'coverage'],
    queryFn: api.getShippingCoverage,
    enabled,
  });
}

export function useShippingZones(enabled = true) {
  return useQuery({
    queryKey: [...CONFIG_KEY, 'zones'],
    queryFn: api.listZones,
    enabled,
  });
}

export function useSaveZone() {
  return useShippingConfigMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    api.saveZone(id, body),
  );
}

export function useDeleteZone() {
  return useShippingConfigMutation((id: string) => api.deleteZone(id));
}

export function useAdminShippingMethods(enabled = true) {
  return useQuery({
    queryKey: [...CONFIG_KEY, 'methods'],
    queryFn: api.listAdminMethods,
    enabled,
  });
}

export function useSaveMethod() {
  return useShippingConfigMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    api.saveMethod(id, body),
  );
}

export function useDeleteMethod() {
  return useShippingConfigMutation((id: string) => api.deleteMethod(id));
}

export function useShippingRates(enabled = true) {
  return useQuery({
    queryKey: [...CONFIG_KEY, 'rates'],
    queryFn: api.listRates,
    enabled,
  });
}

export function useSaveRate() {
  return useShippingConfigMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    api.saveRate(id, body),
  );
}

export function useDeleteRate() {
  return useShippingConfigMutation((id: string) => api.deleteRate(id));
}
