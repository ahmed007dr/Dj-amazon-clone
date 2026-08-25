import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { confirmEmailChange } from '@/features/auth/api';
import { isApiError, setAccessToken } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AuthPage.css';

type State = 'checking' | 'done' | 'failed';

/**
 * Step two of changing the account email.
 *
 * ⚠️  **The path is `/auth/confirm-email` because that is what the server
 *     emails** — `accounts/api.py` builds the link as
 *     `frontend_url("/auth/confirm-email?token=…")`. This page existed nowhere,
 *     so the link led to the SPA's catch-all and the address never changed. The
 *     request half of the flow worked, which made the whole thing look like a
 *     mail delivery problem rather than a missing screen.
 *
 *     Renaming this route means editing that line too, or the link dies again.
 *
 * ⚠️  **No `RequireAuth`.** The link is opened in whatever browser reads the new
 *     mailbox — frequently another device entirely. Demanding a session here
 *     would block the one person who can prove they own the new address.
 */
export function ConfirmEmailChangePage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();

  const token = params.get('token');
  const [state, setState] = useState<State>('checking');
  const [message, setMessage] = useState('');

  // ⚠️  The token is single-use. React's development strict mode mounts effects
  //     twice, and without this guard the second call consumes an already-spent
  //     token and reports failure for a change that in fact succeeded.
  const attempted = useRef(false);

  useEffect(() => {
    if (!token) {
      setState('failed');
      setMessage(t('auth.missingToken'));
      return;
    }

    if (attempted.current) return;
    attempted.current = true;

    void (async () => {
      try {
        await confirmEmailChange(token);

        // ⚠️  The server invalidated every session — the email is the identifier,
        //     so the token held here now names an account that no longer answers
        //     to it. Clearing it locally prevents the next request from being
        //     sent with a credential the server has already rejected.
        setAccessToken(null);
        setState('done');
      } catch (cause) {
        setState('failed');
        setMessage(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
      }
    })();
  }, [token, t]);

  if (state === 'checking') return <Spinner label={t('auth.confirmingEmail')} />;

  if (state === 'failed') {
    return (
      <div className="container">
        <StateMessage
          icon="⚠"
          title={t('auth.emailChangeFailed')}
          body={message}
          action={
            <Button variant="secondary">
              <Link to="/account/security" className="auth-page__link">
                {t('auth.backToSecurity')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="container auth-page">
      <div className="auth-page__card surface">
        <p className="auth-page__icon" aria-hidden>
          ✓
        </p>
        <h1 className="auth-page__title">{t('auth.emailChanged')}</h1>
        <p className="auth-page__body muted">{t('auth.emailChangedBody')}</p>

        <Button
          block
          onClick={() => {
            // ⚠️  A full reload rather than a client navigation: the session was
            //     cleared outside `AuthProvider`, which still holds the old user
            //     in memory and would render the signed-in shell for an account
            //     that no longer exists under that address.
            window.location.assign('/login');
          }}
        >
          {t('auth.signIn')}
        </Button>
      </div>
    </div>
  );
}
