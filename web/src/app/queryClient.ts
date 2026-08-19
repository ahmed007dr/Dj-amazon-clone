import { QueryClient } from '@tanstack/react-query';

import { isApiError } from '@/shared/http';

/**
 * Data-fetching layer configuration.
 *
 * ⚠️  Client errors are never retried.
 *
 *     Repeating a call that returns 404 or 403 three times triples the delay
 *     before the error message appears, with no chance of success. Only a
 *     failing server or a dropped network is worth a retry.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (isApiError(error) && !error.isRetryable) return false;
        return failureCount < 2;
      },
      staleTime: 60 * 1000,
      // ⚠️  No refetch on every tab focus: on a mobile connection that means
      //     spending the user's data on a refresh they never asked for.
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
