import { http } from '@/shared/http';

/**
 * حركة الاستخدام — **قراءة فقط**.
 *
 * ⚠️  ثلاثة أرقام لا رقم واحد في نبض اللحظة.
 *
 *     «١٢ متصفّحًا مجهولًا» و«٣ مسجَّلين» قراران مختلفان تمامًا في
 *     التشغيل، ومجموعهما «١٥» لا يقول أيًّا منهما. ولذلك الحقول
 *     الثلاثة تصل منفصلة ولا تُجمع في الواجهة.
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

/** خلية واحدة في شبكة ٧×٢٤ — الشبكة مكتملة دائمًا من الخادم. */
export interface TrafficCell {
  weekday: number;
  hour: number;
  requests: number;
  visitors: number;
}

export interface TrafficPeakHours {
  start: string;
  end: string;
  /** المنطقة الزمنية التي حُسبت بها الساعات — تُعرَض كي لا يُقرأ الرقم خطأً. */
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
