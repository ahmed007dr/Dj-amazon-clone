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
 * أجهزتي المتصلة.
 *
 * ⚠️  الشاشة كانت **تعرض ولا تُنهي** — وهذا أسوأ من عدم العرض:
 *     المستخدم يرى جهازًا لا يعرفه ولا يملك ما يفعله حياله.
 *
 * ⚠️  والجلسة الحالية **لا زر لها**.
 *
 *     إنهاؤها يخرج المستخدم من الشاشة التي يقف عليها الآن — وهو
 *     أثر مفاجئ لزر يبدو كبقية أخواته. الخروج له مكانه في القائمة.
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

            {/* ⚠️  عنوان IP معروض عمدًا: هو ما يجعل المستخدم يميّز
                جهازه من غيره — «هاتف» وحدها لا تكفي. */}
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
