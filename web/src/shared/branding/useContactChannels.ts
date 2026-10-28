/**
 * The public contact channels, resolved for the visitor's language.
 *
 * ⚠️  Language is resolved **here**, from data already in memory, so switching it is
 *     instant and needs no request (the same rule as `useLocalizedMap`). The one thing
 *     that differs per language besides the label is the WhatsApp link: its prefilled
 *     message is Arabic in `href` and English in `href_en`.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useTheme } from '@/shared/theme';
import type { ChannelKind } from '@/shared/theme/types';

export interface ResolvedChannel {
  /** Stable within a payload: the same link never appears twice in one list. */
  key: string;
  kind: ChannelKind;
  label: string;
  value: string;
  href: string;
  floating: boolean;
}

export function useContactChannels(): ResolvedChannel[] {
  const { theme } = useTheme();
  const { i18n } = useTranslation();
  const locale = i18n.language.slice(0, 2);

  const channels = theme?.contact_channels;

  return useMemo(
    () =>
      (channels ?? []).map((channel, index) => ({
        // The server sends no ids on purpose; kind + position is unique and stable enough
        key: `${channel.kind}-${index}`,
        kind: channel.kind,
        label: channel.label[locale] || channel.label.ar || '',
        value: channel.value,
        href: (locale === 'en' && channel.href_en) || channel.href,
        floating: channel.floating,
      })),
    [channels, locale],
  );
}
