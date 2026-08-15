import { http } from '@/shared/http';

import type {
  Notification,
  NotificationCategory,
  NotificationChannel,
  NotificationPreference,
} from './types';

interface CursorPage<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

export const listNotifications = (params?: { unread?: boolean; category?: string }) =>
  http.get<CursorPage<Notification>>('/notifications/', {
    params: {
      // ⚠️  `'true'` نصًّا: الخادم يقارن بالنص لا بالمنطقي
      unread: params?.unread ? 'true' : undefined,
      category: params?.category,
    },
  });

export const getUnreadCount = () =>
  http.get<{ unread: number }>('/notifications/unread-count/');

export const markRead = (id: string) =>
  http.post<Notification>(`/notifications/${id}/read/`);

export const markAllRead = () => http.post<{ marked: number }>('/notifications/read-all/');

export const listPreferences = () =>
  http.get<NotificationPreference[]>('/notifications/preferences/');

export const setPreference = (payload: {
  category: NotificationCategory;
  channel: NotificationChannel;
  is_enabled: boolean;
}) => http.post<unknown>('/notifications/preferences/', payload);
