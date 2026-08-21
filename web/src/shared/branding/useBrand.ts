/**
 * The textual identity data — for use in the header, the footer and the page title.
 *
 * ⚠️  The name, the wordmark and the contact details are read in many places.
 *     Passing them as props from the root means a `props` chain crossing five
 *     layers to reach the footer.
 */

import { useLocalizedMap } from '@/shared/i18n/useLocalized';
import { useTheme } from '@/shared/theme';

export function useBrand() {
  const { theme } = useTheme();
  const localized = useLocalizedMap();

  return {
    name: localized(theme?.name),
    tagline: localized(theme?.tagline),
    address: localized(theme?.contact.address),
    contact: theme?.contact,
    social: theme?.social ?? {},
    assets: theme?.assets,
  };
}
