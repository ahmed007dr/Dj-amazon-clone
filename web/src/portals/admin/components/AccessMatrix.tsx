import { useTranslation } from 'react-i18next';

import { useAccessMatrix } from '@/features/settings/api';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AccessMatrix.css';

/**
 * مصفوفة «من يرى ماذا».
 *
 * ⚠️  **أداة تشخيص لا تقرير.**
 *
 *     السؤال الذي تجيبه: «لماذا لا يرى الطالب هذا المنتج؟» —
 *     وتجربة كل تركيبة يدويًا (تسجيل خروج · حساب تجريبي · بحث)
 *     تستغرق دقائق وتُخطئ. الجدول يجيب في نظرة.
 *
 * ⚠️  و**خانتان لكل نوع: قبل التوثيق وبعده**.
 *
 *     أغلب سياسات المهنيين تسمح بعد التوثيق وتمنع قبله. خانة
 *     واحدة تُخفي أهم فرق في النظام كله، وتجعل «الصيدلي ممنوع»
 *     تبدو قاعدة بينما هي حالة انتظار.
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

      {/* ⚠️  التمرير داخل حاوية لا في الصفحة: الأنواع تسعة، والجدول
          أعرض من أي هاتف — وتمرير الصفحة أفقيًا يكسر باقي الشاشة. */}
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

                  // الزائر بلا حالة توثيق — خانة واحدة تكفيه
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
