import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type { BundleFilters } from './types';

const PROFILE_KEY = ['academic', 'me'] as const;

/**
 * The public bundles list, narrowed by the visitor's filters.
 *
 * ⚠️  The filters are part of the key, so each combination is cached on its own
 *     and going back to a previous filter is instant.
 *
 * ⚠️  `keepPreviousData`: while a new filter loads, the old cards stay on screen
 *     (dimmed by the page) instead of collapsing to a spinner and jumping the
 *     page back to the top on every select change.
 */
export function useBundles(filters: BundleFilters) {
  return useQuery({
    queryKey: ['academic', 'bundles', filters],
    queryFn: () => api.getBundles(filters),
    placeholderData: keepPreviousData,
    // Bundles change at the start of a term, not during the day
    staleTime: 10 * 60 * 1000,
  });
}

export function useMyBundles(enabled = true) {
  return useQuery({
    queryKey: ['academic', 'my-bundles'],
    queryFn: api.getMyBundles,
    enabled,
    // Bundles change at the start of a term, not during the day
    staleTime: 10 * 60 * 1000,
  });
}

export function useBundle(slug: string | undefined) {
  return useQuery({
    queryKey: ['academic', 'bundle', slug],
    queryFn: () => api.getBundle(slug as string),
    enabled: Boolean(slug),
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * ⚠️  The server returns `null` with a `200` status for non-students, not a `404`.
 *
 *     So `data` may be `null` with no error present — and the check must be on
 *     the value, not on `error`.
 */
export function useStudentProfile(enabled = true) {
  return useQuery({
    queryKey: PROFILE_KEY,
    queryFn: api.getMyStudentProfile,
    enabled,
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * The university tree.
 *
 * ⚠️  A `staleTime` of a full hour — universities and faculties do not change
 *     during a session, and the tree is the heaviest response on the screen.
 *     Refetching it on every window focus is pure waste on a student's connection.
 */
export function useUniversities(enabled = true) {
  return useQuery({
    queryKey: ['academic', 'universities'],
    queryFn: api.getUniversities,
    enabled,
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * ⚠️  Invalidate "my bundles" along with the profile.
 *
 *     `my-bundles` is selected by faculty and year, so changing either makes the
 *     cached list another faculty's. The **public** list (`['academic','bundles']`)
 *     does not depend on the profile — it is the same for every caller — so it is
 *     deliberately left alone: refetching every cached filter combination because
 *     a student corrected their year would be waste. (The page's "My faculty"
 *     shortcut reads the profile itself, which is invalidated here.)
 */
function invalidateAcademic(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: PROFILE_KEY });
  void queryClient.invalidateQueries({ queryKey: ['academic', 'my-bundles'] });
}

export function useCreateStudentProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createStudentProfile,
    onSuccess: () => {
      invalidateAcademic(queryClient);
    },
  });
}

export function useUpdateStudentProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.updateStudentProfile,
    onSuccess: () => {
      invalidateAcademic(queryClient);
    },
  });
}
