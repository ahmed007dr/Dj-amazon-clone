import { http } from '@/shared/http';

import type {
  BundleFilters,
  BundleSummary,
  StudentProfile,
  StudentProfilePayload,
  StudyBundle,
  University,
} from './types';

/**
 * Every active bundle — **for everyone, signed in or not**.
 *
 * ⚠️  Not scoped to the caller's faculty: narrowing is the visitor's choice,
 *     made with the filters (university, faculty, year, kind), and nothing is
 *     applied by default. The server validates every filter (`400` on a
 *     malformed value) and does the narrowing — the browser never downloads
 *     every faculty's bundles to hide most of them.
 */
export const getBundles = (filters: BundleFilters = {}) =>
  http.get<BundleSummary[]>('/academic/bundles/', { params: { ...filters } });

/**
 * The current student's own faculty-and-year bundles.
 *
 * ⚠️  No longer what the bundles page lists: that is `getBundles`, for everyone.
 *     The server still selects these from **the student's faculty and year**, and
 *     the page's "My faculty" shortcut fills the public filters with the same
 *     faculty and year from the profile.
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
