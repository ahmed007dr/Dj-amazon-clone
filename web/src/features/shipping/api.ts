import { http } from '@/shared/http';

/**
 * Shipping — the customer's side and the operator's side.
 *
 * ⚠️  This file did not exist. The server has served `/shipping/` since the
 *     domain was written, and nothing in the frontend ever called it: the
 *     customer could not see a delivery option or follow a shipment, and the
 *     operator had no screen at all. `manage.py api_coverage` is what surfaced
 *     it — four endpoints answering correctly to nobody.
 */

export type ShipmentStatus =
  | 'PENDING'
  | 'PICKED'
  | 'IN_TRANSIT'
  | 'OUT_FOR_DELIVERY'
  | 'DELIVERED'
  | 'FAILED'
  | 'RETURNED';

/**
 * ⚠️  Mirrors `shipping/services.py:ALLOWED_TRANSITIONS`.
 *
 *     The server is the authority and refuses a disallowed move with 409 — a
 *     delivered shipment does not go back to processing, or every delivery
 *     report is corrupted. This copy exists so the screen offers only the moves
 *     that can succeed; it narrows the buttons, it does not grant anything.
 *
 *     A divergence shows as a 409 the operator can see, never as a silent
 *     acceptance, because the server checks again regardless of what is here.
 */
export const ALLOWED_TRANSITIONS: Record<ShipmentStatus, ShipmentStatus[]> = {
  PENDING: ['PICKED', 'FAILED'],
  PICKED: ['IN_TRANSIT', 'FAILED'],
  IN_TRANSIT: ['OUT_FOR_DELIVERY', 'FAILED'],
  OUT_FOR_DELIVERY: ['DELIVERED', 'FAILED'],
  FAILED: ['OUT_FOR_DELIVERY', 'RETURNED'],
  DELIVERED: [],
  RETURNED: [],
};

export interface ShipmentEvent {
  id: string;
  status: ShipmentStatus;
  note: string;
  location: string;
  created_at: string;
}

/**
 * ⚠️  Neither the full address nor the phone number is here, and that is the
 *     server's decision, not an omission: the tracking number is shared with
 *     whoever receives on the customer's behalf, so the payload carries the
 *     governorate and the city and nothing more personal than that.
 */
export interface Shipment {
  id: string;
  number: string;
  status: ShipmentStatus;
  method_name: string;
  governorate: string;
  city: string;
  shipping_fee: string;
  carrier: string;
  tracking_number: string;
  shipped_at: string | null;
  delivered_at: string | null;
  events: ShipmentEvent[];
}

export interface ShippingMethod {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  estimated_days_min: number;
  estimated_days_max: number;
  is_pickup: boolean;
}

export interface PagedShipments {
  results: Shipment[];
  count: number;
  page: number;
  pages: number;
  next: string | null;
  previous: string | null;
}

export interface AdminShipmentQuery {
  status?: string;
  page?: number;
}

// ── Public ─────────────────────────────────────────────────

export const listShippingMethods = () =>
  http.get<ShippingMethod[]>('/shipping/methods/');

/**
 * ⚠️  Public by design, and by number rather than by id.
 *
 *     The recipient is often not the buyer, and they hold the number alone.
 *     Requiring a session here would mean the person actually waiting for the
 *     parcel cannot look it up.
 */
export const trackShipment = (number: string) =>
  http.get<Shipment>(`/shipping/track/${number}/`);

// ── Admin ──────────────────────────────────────────────────

export const listAdminShipments = (params: AdminShipmentQuery) =>
  http.get<PagedShipments>('/shipping/admin/shipments/', { params: { ...params } });

export const transitionShipment = (
  id: string,
  body: {
    status: ShipmentStatus;
    note?: string;
    location?: string;
    tracking_number?: string;
  },
) => http.post<Shipment>(`/shipping/admin/shipments/${id}/transition/`, body);
