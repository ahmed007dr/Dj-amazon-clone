import {
  useInfiniteQuery,
  useMutation,
  useMutationState,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { useToast } from '@/shared/ui/useToast';

import * as api from './api';
import type {
  NotificationCategory,
  NotificationChannel,
  NotificationPreference,
} from './types';

const LIST_KEY = ['notifications', 'list'] as const;
const COUNT_KEY = ['notifications', 'unread-count'] as const;
const PREFERENCES_KEY = ['notifications', 'preferences'] as const;
const SET_PREFERENCE_KEY = ['notifications', 'set-preference'] as const;

/** The raw cursor from the next-page URL (the server returns the full URL). */
function cursorFrom(next: string | null): string | undefined {
  if (!next) return undefined;
  return new URL(next, window.location.origin).searchParams.get('cursor') ?? undefined;
}

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

/**
 * The inbox, a page at a time.
 *
 * ⚠️  Infinite, because the server paginates with a **cursor** (no `count`, no page
 *     numbers — ADR-32). Showing only the first page silently hides everything
 *     older, and the user concludes their history is gone.
 */
export function useNotifications(params?: { unread?: boolean }, enabled = true) {
  return useInfiniteQuery({
    queryKey: [...LIST_KEY, params?.unread ?? false],
    queryFn: ({ pageParam }) =>
      api.listNotifications({
        ...params,
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => cursorFrom(last.next),
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

type PreferenceChange = {
  category: NotificationCategory;
  channel: NotificationChannel;
  is_enabled: boolean;
};

/** One row's identity — what "this switch" means to the pending tracking. */
export const preferenceKey = (row: Pick<PreferenceChange, 'category' | 'channel'>) =>
  `${row.category}:${row.channel}`;

function patchPreference(
  rows: NotificationPreference[] | undefined,
  change: PreferenceChange,
): NotificationPreference[] | undefined {
  return rows?.map((row) =>
    row.category === change.category && row.channel === change.channel
      ? { ...row, is_enabled: change.is_enabled }
      : row,
  );
}

/**
 * Saving one switch.
 *
 * ⚠️  **Optimistic, and rolled back per row.**
 *
 *     The switch flips the instant it is pressed — waiting a round trip for a
 *     toggle makes it feel broken, and the user presses it again. If the server
 *     refuses, only *that* row returns to its old value: restoring a snapshot of
 *     the whole list would also undo a sibling switch whose own request is still
 *     in flight.
 *
 * ⚠️  **No refetch of the list on success.** The list used to be refetched after
 *     every toggle, so the whole screen flickered to a spinner for a change to one
 *     row. The cache is marked stale instead (`refetchType: 'none'`) so the next
 *     visit still reads the server's truth.
 *
 * ⚠️  The toasts live here, not at the call site: `mutate()`'s per-call callbacks
 *     only fire for the *latest* call, so two quick toggles would lose the first
 *     one's confirmation. Options-level callbacks fire for every mutation.
 */
export function useSetPreference() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: SET_PREFERENCE_KEY,
    mutationFn: api.setPreference,
    onMutate: async (change: PreferenceChange) => {
      // An in-flight list fetch would land after this and overwrite the optimistic row
      await queryClient.cancelQueries({ queryKey: PREFERENCES_KEY });
      queryClient.setQueryData<NotificationPreference[]>(PREFERENCES_KEY, (rows) =>
        patchPreference(rows, change),
      );
    },
    onSuccess: () => {
      notify(t('notifications.prefSaved'), 'success');
    },
    onError: (error, change) => {
      queryClient.setQueryData<NotificationPreference[]>(PREFERENCES_KEY, (rows) =>
        patchPreference(rows, { ...change, is_enabled: !change.is_enabled }),
      );
      notify(isApiError(error) ? error.displayMessage : t('notifications.prefError'), 'danger');
    },
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: PREFERENCES_KEY, refetchType: 'none' }),
  });
}

/**
 * Which switches have a save in flight — keys from `preferenceKey`.
 *
 * ⚠️  Per switch, not "the mutation is pending". One `useMutation` observer only
 *     reports its latest call, and the old code used that to disable **every**
 *     checkbox while any one saved. Reading the cache's pending mutations lets
 *     each switch show its own spinner and leaves the others usable.
 */
export function usePendingPreferences(): ReadonlySet<string> {
  const pending = useMutationState({
    filters: { mutationKey: SET_PREFERENCE_KEY, status: 'pending' },
    select: (mutation) => mutation.state.variables as PreferenceChange,
  });

  return new Set(pending.map(preferenceKey));
}
