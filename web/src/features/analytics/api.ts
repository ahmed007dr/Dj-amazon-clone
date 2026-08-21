import { http } from '@/shared/http';

/**
 * Usage traffic — **read-only**.
 *
 * ⚠️  Three numbers, not one, in the live pulse.
 *
 *     "12 anonymous browsers" and "3 registered" are entirely different
 *     operational decisions, and their sum, "15", says neither. So the three
 *     fields arrive separately and are never added together in the frontend.
 */

export interface LivePulse {
  window_minutes: number;
  users_online: number;
  guests_online: number;
  total_online: number;
}

export interface DeviceRow {
  device_type: string;
  requests: number;
  guest_visitors: number;
  known_visitors: number;
}

export interface TrafficSummary {
  start: string;
  end: string;
  requests: number;
  guest_visitors: number;
  known_visitors: number;
  by_device: DeviceRow[];
}

/** One cell in a 7×24 grid — the grid always arrives complete from the server. */
export interface TrafficCell {
  weekday: number;
  hour: number;
  requests: number;
  visitors: number;
}

export interface TrafficPeakHours {
  start: string;
  end: string;
  /** The timezone the hours were computed in — displayed so the figure is not misread. */
  timezone: string;
  cells: TrafficCell[];
  peak_cell: TrafficCell | null;
}

export interface AnalyticsPeriod {
  start?: string;
  end?: string;
}

export const getLivePulse = () => http.get<LivePulse>('/analytics/live/');

export const getTraffic = (params: AnalyticsPeriod = {}) =>
  http.get<TrafficSummary>('/analytics/traffic/', { params: { ...params } });

export const getTrafficPeakHours = (params: AnalyticsPeriod = {}) =>
  http.get<TrafficPeakHours>('/analytics/peak-hours/', { params: { ...params } });
