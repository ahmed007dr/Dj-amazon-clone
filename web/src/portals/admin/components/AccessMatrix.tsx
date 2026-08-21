import { useTranslation } from 'react-i18next';

import { useAccessMatrix } from '@/features/settings/api';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AccessMatrix.css';

/**
 * The "who sees what" matrix.
 *
 * ⚠️  **A diagnostic tool, not a report.**
 *
 *     The question it answers: "why does a student not see this product?" — and
 *     trying every combination by hand (logging out · a test account ·
 *     searching) takes minutes and gets it wrong. The table answers at a glance.
 *
 * ⚠️  And **two cells per type: before verification and after**.
 *
 *     Most professional policies permit after verification and block before it.
 *     A single cell hides the most important distinction in the whole system,
 *     and makes "the pharmacist is blocked" look like a rule when it is a
 *     waiting state.
 */
export function AccessMatrix() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const matrix = useAccessMatrix();

  if (matrix.isPending) return <Spinner />;

  if (!matrix.data || matrix.data.policies.length === 0) {
    return (
      <StateMessage icon="🔐" title={t('access.noPolicies')} body={t('access.noPoliciesBody')} />
    );
  }

  const { account_types: accountTypes, policies } = matrix.data;

  return (
    <section className="access-matrix">
      <p className="muted">{t('access.matrixHint')}</p>

      {/* ⚠️  Scrolling inside a container rather than on the page: there are nine
          types and the table is wider than any phone — and scrolling the page
          horizontally breaks the rest of the screen. */}
      <div className="access-matrix__scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('access.policy')}</th>
              {accountTypes.map((type) => (
                <th key={type} scope="col">
                  {t(`accountType.${type}`, { defaultValue: type })}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {policies.map((row) => (
              <tr key={row.policy.id}>
                <th scope="row">
                  <span className="access-matrix__policy">
                    <strong>{localized(row.policy, 'name')}</strong>
                    <code dir="ltr">{row.policy.code}</code>
                    {row.policy.requires_verification ? (
                      <em>{t('access.needsVerification')}</em>
                    ) : null}
                  </span>
                </th>

                {accountTypes.map((type) => {
                  const cell = row.access[type];
                  if (cell === undefined) return <td key={type}>—</td>;

                  // A visitor has no verification status — one cell is enough for them
                  const hasVerified = cell.verified !== undefined;

                  return (
                    <td key={type}>
                      <span className="access-matrix__pair">
                        <span
                          className={cell.unverified ? 'is-allowed' : 'is-denied'}
                          title={t('access.beforeVerification')}
                        >
                          {cell.unverified ? '✓' : '✕'}
                        </span>

                        {hasVerified ? (
                          <span
                            className={cell.verified ? 'is-allowed' : 'is-denied'}
                            title={t('access.afterVerification')}
                          >
                            {cell.verified ? '✓' : '✕'}
                          </span>
                        ) : null}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="access-matrix__legend">{t('access.legend')}</p>
    </section>
  );
}
