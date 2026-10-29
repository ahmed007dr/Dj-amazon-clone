import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { listSessions, revokeSession } from '@/features/auth/api';
import { isApiError } from '@/shared/http/errors';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';
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
  const [page, setPage] = useState(1);

  // ⚠️  `keepPreviousData`: while the next page loads the current one stays on screen,
  //     so the list does not collapse into a spinner and jump the pager under the finger.
  const query = useQuery({
    queryKey: ['auth', 'sessions', page],
    queryFn: () => listSessions(page),
    placeholderData: keepPreviousData,
  });

  const sessions = query.data?.results ?? [];

  // ⚠️  A page past the end is a `404`, not an empty list — revoking a device in another
  //     tab, or on another device, can remove the last page between two clicks. Go back to
  //     the first page rather than showing a failure for a list that is perfectly fine.
  const pastTheEnd =
    page > 1 && query.isError && isApiError(query.error) && query.error.status === 404;

  useEffect(() => {
    if (pastTheEnd) setPage(1);
  }, [pastTheEnd]);

  const revoke = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => {
      notify(t('account.sessionRevoked'), 'success');
      // ⚠️  Ending the only row on the last page leaves that page empty, so the page that
      //     is on screen no longer exists — refetching it would be a guaranteed `404`.
      //     Step back and only mark the pages stale: the previous page, now the active
      //     one, refetches itself because it is invalidated. (A full page is never the
      //     last one, so `length === 1` on page > 1 is exactly that case.)
      const stepBack = page > 1 && sessions.length === 1;
      if (stepBack) setPage(page - 1);
      void queryClient.invalidateQueries({
        queryKey: ['auth', 'sessions'],
        refetchType: stepBack ? 'none' : 'active',
      });
    },
    onError: (error) =>
      notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
  });

  if (query.isPending || pastTheEnd) return <Spinner />;

  if (query.isError && query.data === undefined) {
    return <StateMessage icon="⚠" title={t('state.errorTitle')} />;
  }

  if (sessions.length === 0) {
    return <StateMessage icon="▢" title={t('account.noSessions')} />;
  }

  return (
    <>
      <ul className="session-list" aria-busy={query.isPlaceholderData}>
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

              {/* When this device signed in, as opposed to when it was last seen: a
                  session that signed in last month and was active a minute ago is a
                  long-lived device, and one that signed in an hour ago from an
                  unfamiliar address is the one to look at. */}
              <span className="session__signed muted">
                {t('account.signedInAt', { date: formatDateTime(session.login_at, i18n.language) })}
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

      <Pagination
        page={query.data?.page ?? page}
        pages={query.data?.pages ?? 1}
        onChange={setPage}
      />
    </>
  );
}
