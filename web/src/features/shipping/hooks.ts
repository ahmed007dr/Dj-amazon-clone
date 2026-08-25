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
