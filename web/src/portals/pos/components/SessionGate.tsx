import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useOpenSession, useRegisters } from '@/features/pos/hooks';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './SessionGate.css';

/**
 * Opening the shift.
 *
 * ⚠️  **The opening balance is required explicitly — with no default.**
 *
 *     The float in the drawer in the morning is part of the reconciliation.
 *     Defaulting it to zero makes closing the day show a surplus equal to it, so
 *     the cashier looks as though they added cash of their own — every day.
 */
export function SessionGate() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const registers = useRegisters();
  const open = useOpenSession();

  const [register, setRegister] = useState('');
  const [float, setFloat] = useState('');

  if (registers.isPending) return <Spinner />;

  const available = (registers.data ?? []).filter((row) => !row.has_open_session);

  if (available.length === 0) {
    return (
      <StateMessage
        icon="▣"
        title={t('pos.noRegisters')}
        // ⚠️  A busy device is not a fault: a colleague is working on it right now, and it is
        //     the first case the second-shift cashier meets.
        body={t('pos.noRegistersBody')}
      />
    );
  }

  const submit = () => {
    if (!register || float === '') return;
    open.mutate({ register, float });
  };

  return (
    <div className="session-gate">
      <h1 className="session-gate__title">{t('pos.openSession')}</h1>

      <label className="session-gate__label" htmlFor="pos-register">
        {t('pos.register')}
      </label>
      <select
        id="pos-register"
        className="session-gate__select"
        value={register}
        onChange={(event) => setRegister(event.target.value)}
      >
        <option value="">{t('common.choose')}</option>
        {available.map((row) => (
          <option key={row.id} value={row.id}>
            {localized(row, 'name')} · {row.location_code}
          </option>
        ))}
      </select>

      <Field
        label={t('pos.openingFloat')}
        type="number"
        inputMode="decimal"
        min="0"
        step="0.01"
        value={float}
        hint={t('pos.openingFloatHint')}
        onChange={(event) => setFloat(event.target.value)}
      />

      {open.error ? (
        <Alert tone="danger">
          {isApiError(open.error) ? open.error.displayMessage : t('state.errorTitle')}
        </Alert>
      ) : null}

      <Button
        block
        size="lg"
        loading={open.isPending}
        disabled={!register || float === ''}
        onClick={submit}
      >
        {t('pos.startShift')}
      </Button>
    </div>
  );
}
