import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useCan } from '@/features/auth/useCan';
import { StateMessage } from '@/shared/ui/StateMessage';

/**
 * A screen guard by permission.
 *
 * ⚠️  **The link disappears and the screen explains — it does not disappear too.**
 *
 *     Whoever arrives by the direct path (a saved link · one shared by a
 *     colleague) must read "this screen needs a permission", not "page not
 *     found". The second makes them report a broken link, and the first makes
 *     them ask their manager for the permission — which is exactly what we want.
 *
 * ⚠️  And **the message names the screen**: "you need a permission" with no name
 *     cannot be relayed to whoever grants it.
 */
export function RequirePermission({
  permission,
  screen,
  children,
}: {
  permission: string;
  /** The translation key for the screen's name — named in the message so it can be requested by name. */
  screen?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const can = useCan();

  if (!can(permission)) {
    return (
      <StateMessage
        icon="🔒"
        title={t('state.forbiddenTitle')}
        body={
          screen
            ? t('state.forbiddenScreen', { screen: t(screen) })
            : t('state.forbiddenBody')
        }
      />
    );
  }

  return children;
}
