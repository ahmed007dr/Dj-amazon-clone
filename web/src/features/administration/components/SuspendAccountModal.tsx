import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Modal } from '@/shared/ui/Modal';
import { useToast } from '@/shared/ui/useToast';

import { activateAccount, suspendAccount, type AdminAccount } from '../api';

import './SuspendAccountModal.css';

/**
 * Suspend or reactivate an account.
 *
 * ⚠️  **The effect is immediate** — the sessions are revoked and the tokens
 *     cancelled now, not when they expire. Saying so on the screen lets the
 *     admin know what they are doing.
 *
 * ⚠️  And the difference between "suspended" and "banned" is not cosmetic: the
 *     first is temporary and liftable, the second final. Conflating them makes
 *     every suspension look final.
 */
export function SuspendAccountModal({
  account,
  onClose,
}: {
  account: AdminAccount | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const [reason, setReason] = useState('');
  const [status, setStatus] = useState<'SUSPENDED' | 'BLOCKED'>('SUSPENDED');
  const [error, setError] = useState<string | null>(null);

  const isSuspended = account?.status !== 'ACTIVE';

  const mutation = useMutation({
    mutationFn: () => {
      if (!account) throw new Error('no account');
      return isSuspended
        ? activateAccount(account.id, reason)
        : suspendAccount(account.id, reason, status);
    },
    onSuccess: () => {
      notify(isSuspended ? t('admin.accountActivated') : t('admin.accountSuspended'));
      void queryClient.invalidateQueries({ queryKey: ['admin', 'accounts'] });
      setReason('');
      onClose();
    },
    onError: (cause) => {
      setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
    },
  });

  if (!account) return null;

  return (
    <Modal
      open
      onClose={onClose}
      title={isSuspended ? t('admin.activateAccount') : t('admin.suspendAccount')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={isSuspended ? 'primary' : 'danger'}
            loading={mutation.isPending}
            disabled={!isSuspended && reason.trim().length < 3}
            onClick={() => {
              setError(null);
              mutation.mutate();
            }}
          >
            {t('common.confirm')}
          </Button>
        </>
      }
    >
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <p className="suspend__target">
        <strong>{account.full_name}</strong>
        <span className="muted" style={{ direction: 'ltr' }}>
          {account.email}
        </span>
      </p>

      {!isSuspended ? (
        <>
          <Alert tone="warning">{t('admin.suspendWarning')}</Alert>

          <div className="suspend__modes" role="radiogroup" aria-label={t('admin.suspendKind')}>
            <label className={`suspend__mode ${status === 'SUSPENDED' ? 'is-selected' : ''}`}>
              <input
                type="radio"
                name="suspend-kind"
                checked={status === 'SUSPENDED'}
                onChange={() => {
                  setStatus('SUSPENDED');
                }}
              />
              <span>
                <strong>{t('admin.suspendTemporary')}</strong>
                <span className="muted">{t('admin.suspendTemporaryHint')}</span>
              </span>
            </label>

            <label className={`suspend__mode ${status === 'BLOCKED' ? 'is-selected' : ''}`}>
              <input
                type="radio"
                name="suspend-kind"
                checked={status === 'BLOCKED'}
                onChange={() => {
                  setStatus('BLOCKED');
                }}
              />
              <span>
                <strong>{t('admin.suspendPermanent')}</strong>
                <span className="muted">{t('admin.suspendPermanentHint')}</span>
              </span>
            </label>
          </div>
        </>
      ) : null}

      <label className="suspend__label" htmlFor="suspend-reason">
        {t('admin.reason')}
        {!isSuspended ? ' *' : ''}
      </label>
      <textarea
        id="suspend-reason"
        className="suspend__input"
        rows={3}
        maxLength={500}
        value={reason}
        placeholder={t('admin.reasonPlaceholder')}
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />
    </Modal>
  );
}
