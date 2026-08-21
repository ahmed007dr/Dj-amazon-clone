import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { listSessions, revokeSession } from '@/features/auth/api';
import { isApiError } from '@/shared/http/errors';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';
import { formatDateTime } from '@/shared/utils/format';

import './SessionList.css';

/**
 * My connected devices.
 *
 * ⚠️  The screen used to **display and not end** — and that is worse than not
 *     displaying: the user sees a device they do not recognise and has nothing
 *     they can do about it.
 *
 * ⚠️  And the current session **has no button**.
 *
 *     Ending it logs the user out of the very screen they are standing on — a
 *     surprising effect for a button that looks like all its siblings. Logging
 *     out has its own place in the menu.
 */
export function SessionList() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const query = useQuery({ queryKey: ['auth', 'sessions'], queryFn: listSessions });

  const revoke = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => {
      notify(t('account.sessionRevoked'), 'success');
      void queryClient.invalidateQueries({ queryKey: ['auth', 'sessions'] });
    },
    onError: (error) =>
      notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
  });

  if (query.isPending) return <Spinner />;

  const sessions = query.data ?? [];

  if (sessions.length === 0) {
    return <StateMessage icon="▢" title={t('account.noSessions')} />;
  }

  return (
    <ul className="session-list">
      {sessions.map((session) => (
        <li key={session.id} className="session">
          <div className="session__info">
            <strong className="session__device">
              {t(`deviceType.${session.device_type}`, { defaultValue: session.device_type })}
              {session.is_current ? (
                <Badge tone="success">{t('account.thisDevice')}</Badge>
              ) : null}
            </strong>

            {/* ⚠️  The IP address is shown deliberately: it is what lets the user tell
                their own device from another — "phone" alone is not enough. */}
            <span className="session__meta muted">
              {session.ip_address ?? '—'} · {formatDateTime(session.last_activity, i18n.language)}
            </span>
          </div>

          {!session.is_current ? (
            <Button
              size="sm"
              variant="ghost"
              loading={revoke.isPending}
              onClick={() => revoke.mutate(session.id)}
            >
              {t('account.revokeSession')}
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
