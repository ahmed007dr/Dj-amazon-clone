import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';

const LIST_KEY = ['notifications', 'list'] as const;
const COUNT_KEY = ['notifications', 'unread-count'] as const;
const PREFERENCES_KEY = ['notifications', 'preferences'] as const;

/**
 * عدّاد الجرس.
 *
 * ⚠️  تحديث دوري كل دقيقة لا فوري.
 *
 *     لا يوجد WebSocket في هذه المرحلة، والبديل الوحيد للتحديث
 *     الدوري هو عدّاد يتجمّد حتى يعيد المستخدم تحميل الصفحة —
 *     فيصله إشعار شحن ولا يعرف. ودقيقة كافية: النقطة أن يعرف
 *     خلال دقائق لا خلال أجزاء من الثانية.
 *
 * ⚠️  ويتوقف حين تكون اللسان في الخلفية (`refetchIntervalInBackground`
 *     المتروك على الافتراضي) — لسان منسيّ ينادي الخادم كل دقيقة
 *     ليومٍ كامل حِمل بلا قارئ.
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
    // ⚠️  العدّاد يُبطَل مع القائمة: قراءة إشعار تنقص الرقم في
    //     الجرس، وتركه كما هو يجعل المستخدم يفتح شاشة لا جديد فيها.
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
