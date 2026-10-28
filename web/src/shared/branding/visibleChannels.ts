import type { ChannelKind } from '@/shared/theme/types';

import type { ResolvedChannel } from './useContactChannels';

/** Which legacy `social` key a channel kind duplicates when both hold the same page. */
const SOCIAL_KEY: Partial<Record<ChannelKind, string>> = {
  FACEBOOK: 'facebook',
  INSTAGRAM: 'instagram',
  X: 'x',
  LINKEDIN: 'linkedin',
  YOUTUBE: 'youtube',
  TIKTOK: 'tiktok',
};

const digits = (text: string) => text.replace(/\D/g, '');

/** The same phone line however it was typed: `0221234567` ≡ `+20 22 123 4567`. */
function samePhone(a: string, b: string): boolean {
  const x = digits(a);
  const y = digits(b);
  const length = Math.min(x.length, y.length, 9);
  return length >= 5 && x.slice(-length) === y.slice(-length);
}

const flattenUrl = (url: string) =>
  url
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\/(www\.)?/, '')
    .replace(/\/+$/, '');

/**
 * ⚠️  **Show each way of reaching the store once.**
 *
 *     The email, phone and social links on the identity tab keep rendering, and the
 *     channels are additional. An admin who then adds the same email as a channel (or
 *     the Instagram page that is already under "Follow us") would otherwise see it
 *     twice, one column apart. The legacy field wins — it was there first — and the
 *     channel is the one dropped.
 */
export function visibleChannels(
  channels: ResolvedChannel[],
  legacy: { email?: string | undefined; phone?: string | undefined; social: Record<string, string> },
): ResolvedChannel[] {
  const seen = new Set<string>();

  return channels.filter((channel) => {
    if (channel.kind === 'EMAIL' && legacy.email) {
      if (channel.href.toLowerCase() === `mailto:${legacy.email.toLowerCase()}`) return false;
    }
    if (channel.kind === 'PHONE' && legacy.phone && samePhone(channel.value, legacy.phone)) {
      return false;
    }

    const socialKey = SOCIAL_KEY[channel.kind];
    const legacyUrl = socialKey ? legacy.social[socialKey] : undefined;
    if (legacyUrl && flattenUrl(legacyUrl) === flattenUrl(channel.href)) return false;

    // Two channels with the same link (a WhatsApp added twice) read as a mistake
    if (seen.has(channel.href)) return false;
    seen.add(channel.href);
    return true;
  });
}
