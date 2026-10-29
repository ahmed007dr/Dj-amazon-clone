/**
 * Where the guide lives in the router.
 *
 * ⚠️  Its own tiny module: the header needs this constant on every admin screen, and
 *     `lookup.ts` pulls in the guide's entire text. Keeping the constant here is what
 *     lets that text stay in a lazily loaded chunk.
 */
export const GUIDE_ROOT = '/admin/docs';
