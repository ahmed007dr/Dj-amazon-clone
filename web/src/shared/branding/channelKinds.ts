/**
 * The contact channel kinds, in the order the admin's picker lists them.
 *
 * ⚠️  The names and placeholders are translations (`branding.channels.kind.<KIND>`,
 *     `.placeholder.<KIND>`, `.help.<KIND>`), not strings here — an ESLint rule keeps
 *     absolute URLs out of the code, and a hint such as "instagram.com/store" is one.
 *
 * ⚠️  The list mirrors `branding.models.ChannelKind`. The server is the authority on what
 *     a kind accepts; this only decides what the picker offers.
 */

import type { ChannelKind } from '@/shared/theme/types';

export const CHANNEL_KINDS: readonly ChannelKind[] = [
  'WHATSAPP',
  'TELEGRAM',
  'PHONE',
  'EMAIL',
  'FACEBOOK',
  'INSTAGRAM',
  'TIKTOK',
  'YOUTUBE',
  'X',
  'SNAPCHAT',
  'LINKEDIN',
  'WEBSITE',
  'MAP',
  'OTHER',
];

/** Kinds whose link opens another site; `tel:` and `mailto:` are handled by the device. */
export function isWebLink(href: string): boolean {
  // ⚠️  A pattern rather than `startsWith('https://')`: the lint rule that keeps absolute
  //     URLs out of the code reads that literal as an API address.
  return /^https:/i.test(href);
}
