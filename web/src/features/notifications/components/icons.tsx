import type { ReactNode } from 'react';

import type { NotificationChannel } from '../types';

/**
 * Small inline icons for the preferences screen.
 *
 * ⚠️  SVG with `currentColor`, not text glyphs — the same reasoning as `CartIcon`:
 *     glyphs are drawn differently by every font, SVG takes the surrounding text
 *     colour (so the muted/disabled/dark-mode states need no extra rules).
 *     They are decorative; the label next to them carries the meaning.
 */
function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      width="1.25rem"
      height="1.25rem"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ display: 'block', flexShrink: 0 }}
    >
      {children}
    </svg>
  );
}

const BellIcon = () => (
  <Svg>
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </Svg>
);

const MailIcon = () => (
  <Svg>
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <path d="m22 7-10 6L2 7" />
  </Svg>
);

const MessageIcon = () => (
  <Svg>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </Svg>
);

const PhoneIcon = () => (
  <Svg>
    <rect x="6" y="2" width="12" height="20" rx="2" />
    <path d="M11 18h2" />
  </Svg>
);

/** The icon for a delivery channel. */
export function ChannelIcon({ channel }: { channel: NotificationChannel }) {
  switch (channel) {
    case 'IN_APP':
      return <BellIcon />;
    case 'EMAIL':
      return <MailIcon />;
    case 'PUSH':
      return <PhoneIcon />;
    case 'SMS':
    case 'WHATSAPP':
      return <MessageIcon />;
  }
}

/** The lock shown on a preference that cannot be turned off. */
export function LockIcon() {
  return (
    <svg
      width="0.875em"
      height="0.875em"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0 }}
    >
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}
