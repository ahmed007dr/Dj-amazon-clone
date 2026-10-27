import { useQuery } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * Public switches read once on load (`GET /public-config/`).
 *
 * ⚠️  **Every switch defaults to off while loading and on failure.** A student
 *     must not see a "pending verification" notice for the half second before
 *     the answer arrives, and a failed request must not switch an enforcement on.
 */
export interface PublicConfig {
  student_verification_enforced: boolean;
}

const OFF: PublicConfig = { student_verification_enforced: false };

export function usePublicConfig(): PublicConfig {
  const query = useQuery({
    queryKey: ['public-config'],
    queryFn: () => http.get<PublicConfig>('/public-config/'),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return query.data ?? OFF;
}

/** Whether student verification is a requirement (off = say nothing about it). */
export function useStudentVerificationEnforced(): boolean {
  return usePublicConfig().student_verification_enforced;
}
