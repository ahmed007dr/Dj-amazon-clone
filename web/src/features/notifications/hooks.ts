import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';

const LIST_KEY = ['notifications', 'list'] as const;
const COUNT_KEY = ['notifications', 'unread-count'] as const;
const PREFERENCES_KEY = ['notifications', 'preferences'] as const;

/**
 * The bell counter.
 *
 * ⚠️  Polling every minute rather than live updates.
 *
 *     There is no WebSocket at this stage, and the only alternative to polling
 *     is a counter frozen until the user reloads the page — so a shipping
 *     notification arrives and they never know. And a minute is enough: the
 *     point is that they learn within minutes, not within fractions of a second.
 *
 * ⚠️  And it stops while the tab is in the background
 *     (`refetchIntervalInBackground` left on its default) — a forgotten tab
 *     calling the server every minute for a whole day is load with no reader.
 */
export function useUnreadCount(enabled = true) {
  return useQuery({
    queryKey: COUNT_KEY,
    queryFn: api.getUnreadCount,
    enabled,
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  });
}

export function useNotifications(params?: { unread?: boolean }, enabled = true) {
  return useQuery({
    queryKey: [...LIST_KEY, params?.unread ?? false],
    queryFn: () => api.listNotifications(params),
    enabled,
    staleTime: 30 * 1000,
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.markRead,
    // ⚠️  The counter is invalidated along with the list: reading a notification
    //     lowers the number on the bell, and leaving it makes the user open a screen with nothing new in it.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
      void queryClient.invalidateQueries({ queryKey: COUNT_KEY });
    },
  });
}

export function useMarkAllRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.markAllRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
      void queryClient.invalidateQueries({ queryKey: COUNT_KEY });
    },
  });
}

export function usePreferences(enabled = true) {
  return useQuery({
    queryKey: PREFERENCES_KEY,
    queryFn: api.listPreferences,
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useSetPreference() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.setPreference,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PREFERENCES_KEY });
    },
  });
}
