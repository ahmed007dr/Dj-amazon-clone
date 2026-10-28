import type { JSX } from 'react';

import type { ChannelKind } from '@/shared/theme/types';

/**
 * One small icon per contact channel kind — plain shapes, not traced logo artwork.
 *
 * ⚠️  `currentColor` throughout, never a brand colour: the same icon sits in the footer
 *     (muted text), in a hovered link (primary), on the green floating button (white) and
 *     in the admin list — a hardcoded fill would freeze it in one of them and break dark
 *     mode in another.
 *
 * ⚠️  Decorative (`aria-hidden`): the row always carries the label as text, and the
 *     floating button names itself with `aria-label`. An icon that also announced
 *     itself would be read twice.
 *
 * ⚠️  Symmetric or mirror-safe on purpose — nothing here points left or right, so the
 *     icons need no RTL flipping.
 */

const SHAPES: Record<ChannelKind, () => JSX.Element> = {
  WHATSAPP: () => (
    <>
      <path
        d="M4 20l1.2-4.1A8 8 0 1 1 8.2 19L4 20z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        fill="currentColor"
        d="M9.2 7.9c.3-.3.7-.3.9.1l.7 1.5c.1.3 0 .5-.2.7l-.5.5c.6 1.1 1.5 2 2.6 2.6l.5-.5c.2-.2.5-.3.7-.2l1.5.7c.4.2.4.6.1.9-.6.8-1.5 1.1-2.4.8a8 8 0 0 1-4.5-4.5c-.3-.9 0-1.7.6-2.3z"
      />
    </>
  ),
  TELEGRAM: () => (
    <>
      <path
        d="M20.5 4.5L3.5 11l5 1.8 1.9 5.7 2.8-3.5 4.3 3.2 3-13.7z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M8.5 12.8l11-7.3-8.6 9" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </>
  ),
  PHONE: () => (
    <path
      d="M6.6 3.5h2.6l1.4 3.7-1.8 1.3a11 11 0 0 0 5.2 5.2l1.3-1.8 3.7 1.4v2.6a2 2 0 0 1-2.2 2A14.5 14.5 0 0 1 4.6 5.7a2 2 0 0 1 2-2.2z"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinejoin="round"
    />
  ),
  EMAIL: () => (
    <>
      <rect x="3" y="5.5" width="18" height="13" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4 7.5l8 6 8-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </>
  ),
  FACEBOOK: () => (
    <path
      fill="currentColor"
      d="M14 13.5h2.5l.4-3H14V8.5c0-.9.2-1.5 1.5-1.5H17V4.2C16.7 4.1 15.7 4 14.5 4 12 4 10.5 5.5 10.5 8.2V10.5H8v3h2.5V20h3.5v-6.5z"
    />
  ),
  INSTAGRAM: () => (
    <>
      <rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" />
    </>
  ),
  TIKTOK: () => (
    <path
      fill="currentColor"
      d="M14 4v10.2a2.7 2.7 0 1 1-2.2-2.66V9.1a5.2 5.2 0 1 0 4.7 5.17V9.9c1 .7 2.2 1.1 3.5 1.1V8.5c-1.7 0-3.1-1-3.6-2.5-.2-.6-.3-1.3-.3-2H14z"
    />
  ),
  YOUTUBE: () => (
    <>
      <rect x="3" y="6" width="18" height="12" rx="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path fill="currentColor" d="M10.5 9.5l5 2.5-5 2.5v-5z" />
    </>
  ),
  X: () => (
    <path d="M4 4l16 16M20 4L4 20" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" fill="none" />
  ),
  SNAPCHAT: () => (
    <path
      d="M12 3.5c-2.6 0-4.2 1.9-4.2 4.4v2.4c-.5.2-1.3.3-2 .4.5 1.2 1.3 1.6 2.1 1.8-.3 1-1.2 1.8-2.3 2.2.9.7 1.9.8 2.7 1 .3.6.8 1.1 1.5 1.1.8 0 1.2-.6 2.2-.6s1.4.6 2.2.6c.7 0 1.2-.5 1.5-1.1.8-.2 1.8-.3 2.7-1-1.1-.4-2-1.2-2.3-2.2.8-.2 1.6-.6 2.1-1.8-.7-.1-1.5-.2-2-.4V7.9c0-2.5-1.6-4.4-4.2-4.4z"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinejoin="round"
    />
  ),
  LINKEDIN: () => (
    <>
      <rect x="4" y="9" width="2.6" height="9" fill="currentColor" />
      <circle cx="5.3" cy="5.5" r="1.6" fill="currentColor" />
      <path
        fill="currentColor"
        d="M10 9h2.5v1.5c.7-1.1 1.9-1.8 3.3-1.8 2.6 0 4.2 1.7 4.2 4.9V18h-2.6v-3.8c0-1.7-.6-2.7-2-2.7-1.5 0-2.4 1-2.4 2.7V18H10V9z"
      />
    </>
  ),
  WEBSITE: () => (
    <>
      <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.2 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.2-3.5-8.5S9.6 5.9 12 3.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      />
    </>
  ),
  MAP: () => (
    <>
      <path
        d="M12 21s-6.5-5.8-6.5-11a6.5 6.5 0 0 1 13 0c0 5.2-6.5 11-6.5 11z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="10" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </>
  ),
  // The generic link: two chain links. Also the fallback for a kind this build does not know.
  OTHER: () => (
    <>
      <path
        d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </>
  ),
};

export function ChannelIcon({ kind, size = 20 }: { kind: ChannelKind; size?: number }) {
  // ⚠️  `?? OTHER`: a server newer than this bundle may send a kind we have no shape for —
  //     a generic link icon beats a blank gap in the footer.
  const Shape = SHAPES[kind] ?? SHAPES.OTHER;

  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden focusable="false">
      <Shape />
    </svg>
  );
}
