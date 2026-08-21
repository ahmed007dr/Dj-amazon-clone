import { http } from '@/shared/http';

import type {
  StudentProfile,
  StudentProfilePayload,
  StudyBundle,
  University,
} from './types';

/**
 * The current student's bundles.
 *
 * ⚠️  The server selects them from **their faculty and year** — not the frontend.
 *
 *     Filtering locally means downloading every bundle for every university and
 *     then displaying one, and it also means a student seeing bundles from a
 *     faculty that is not theirs.
 */
export const getMyBundles = () => http.get<StudyBundle[]>('/academic/me/bundles/');

export const getBundle = (slug: string) =>
  http.get<StudyBundle>(`/academic/bundles/${slug}/`);

/**
 * ⚠️  Returns `null` with a `200` status for non-students — not a `404`.
 *
 *     A missing academic profile is a **normal** state, not an error: most
 *     accounts are not student accounts. Treating it as an error shows a fault
 *     message to a user who did nothing wrong.
 */
export const getMyStudentProfile = () => http.get<StudentProfile | null>('/academic/me/');

/**
 * The university tree — **public, with no token**.
 *
 * ⚠️  The server opens it to unregistered visitors deliberately: a student picks
 *     their university before they have an account. So it is not gated here with
 *     an `enabled` flag on the session.
 */
export const getUniversities = () => http.get<University[]>('/academic/universities/');

export const createStudentProfile = (payload: StudentProfilePayload) =>
  http.post<StudentProfile>('/academic/me/', payload);

/**
 * ⚠️  A partial `PATCH`: the student advances their year or corrects their
 *     department without resending the whole hierarchy — and sending an
 *     unchanged field re-runs the consistency check against a stale value, so
 *     the server refuses it for no reason the student can understand.
 */
export const updateStudentProfile = (payload: Partial<StudentProfilePayload>) =>
  http.patch<StudentProfile>('/academic/me/', payload);
