import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { Button } from '@/shared/ui/Button';

import { isAdmin, isStaff, isSuspended } from '../permissions';
import { useAuth } from '../useAuth';

import './AccountMenu.css';

/**
 * The account menu — sign in, or the user's identity.
 *
 * ⚠️  One component for every portal, because its behaviour genuinely **is** the
 *     same: who you are, and how you sign out. The header, the footer and the
 *     logo differ between portals because their content differs; this does not.
 */
export function AccountMenu() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, isRestoring, signOut } = useAuth();

  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);

  // ⚠️  Nothing during the restore: showing "sign in" for a moment and then
  //     replacing it with the name is a flicker suggesting the session dropped.
  if (isRestoring) return <span className="account-menu__placeholder" aria-hidden />;

  if (!user) {
    return (
      <Button variant="secondary" size="sm" onClick={() => void navigate('/login')}>
        {t('nav.login')}
      </Button>
    );
  }

  async function handleSignOut() {
    setPending(true);
    await signOut();
    setOpen(false);
    setPending(false);
    void navigate('/');
  }

  return (
    <div className="account-menu">
      <button
        type="button"
        className="account-menu__trigger"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => {
          setOpen((value) => !value);
        }}
      >
        <span className="account-menu__avatar" aria-hidden>
          {user.full_name.trim().charAt(0) || user.email.charAt(0)}
        </span>
        <span className="account-menu__name truncate desktop-only">{user.full_name}</span>
      </button>

      {open ? (
        <>
          <button
            type="button"
            className="account-menu__scrim"
            aria-label={t('common.close')}
            onClick={() => {
              setOpen(false);
            }}
          />

          <div className="account-menu__panel surface" role="menu">
            <div className="account-menu__identity">
              <strong className="truncate">{user.full_name}</strong>
              <span className="account-menu__email muted truncate">{user.email}</span>
            </div>

            {/* ⚠️  A suspended account is told it is suspended — silence makes them
                assume the system is broken and try again */}
            {isSuspended(user) ? (
              <p className="account-menu__suspended">{t('auth.accountSuspended')}</p>
            ) : null}

            <div className="account-menu__links">
              <Link to="/account" role="menuitem" onClick={() => { setOpen(false); }}>
                {t('nav.account')}
              </Link>
              <Link to="/account/orders" role="menuitem" onClick={() => { setOpen(false); }}>
                {t('nav.orders')}
              </Link>

              {/* Sections the user does not own do not appear at all */}
              {isStaff(user) ? (
                <Link to="/employee" role="menuitem" onClick={() => { setOpen(false); }}>
                  {t('portal.employee')}
                </Link>
              ) : null}
              {isAdmin(user) ? (
                <Link to="/admin" role="menuitem" onClick={() => { setOpen(false); }}>
                  {t('portal.admin')}
                </Link>
              ) : null}
            </div>

            <Button
              variant="ghost"
              size="sm"
              block
              loading={pending}
              onClick={() => void handleSignOut()}
            >
              {t('nav.logout')}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
