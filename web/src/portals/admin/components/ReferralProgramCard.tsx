import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteReferralProgram,
  useSaveReferralProgram,
  useTargetingOptions,
  type ReferralProgram,
} from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './LoyaltyProgramCard.css';

/**
 * بطاقة برنامج إحالة.
 *
 * ⚠️  **نفس شكل بطاقة الولاء ونفس موضع المفتاح.**
 *
 *     بطاقتان لقرارين متشابهين بتخطيطين مختلفين تجعلان الأدمن
 *     يبحث عن المفتاح في كل مرة. التشابه هنا ليس كسلًا — هو ما
 *     يجعل الشاشة تُتعلَّم مرة واحدة.
 */
export function ReferralProgramCard({ program }: { program: ReferralProgram }) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const options = useTargetingOptions();
  const save = useSaveReferralProgram();
  const remove = useDeleteReferralProgram();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(program);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const flip = (list: string[], value: string) =>
    list.includes(value) ? list.filter((row) => row !== value) : [...list, value];

  return (
    <article className={`loyalty-program surface ${program.is_active ? 'is-on' : 'is-off'}`}>
      <header className="loyalty-program__head">
        <div>
          <h3>{localized(program, 'name')}</h3>
          <code dir="ltr">{program.code}</code>
        </div>

        <label className="loyalty-switch">
          <input
            type="checkbox"
            checked={program.is_active}
            disabled={save.isPending}
            onChange={(event) =>
              save.mutate(
                { id: program.id, is_active: event.target.checked },
                { onSuccess: () => notify(t('loyalty.saved'), 'success'), onError: fail },
              )
            }
          />
          <span className="loyalty-switch__track" aria-hidden />
          <span className="loyalty-switch__text">
            {program.is_active ? t('loyalty.on') : t('loyalty.off')}
          </span>
        </label>
      </header>

      <dl className="loyalty-program__facts">
        <div>
          <dt>{t('loyalty.referrerPoints')}</dt>
          <dd dir="ltr">{program.referrer_points}</dd>
        </div>
        <div>
          <dt>{t('loyalty.refereePoints')}</dt>
          <dd dir="ltr">{program.referee_points}</dd>
        </div>
        <div>
          <dt>{t('loyalty.minOrder')}</dt>
          <dd dir="ltr">{program.min_order_amount}</dd>
        </div>
        <div>
          <dt>{t('loyalty.referralCap')}</dt>
          <dd dir="ltr">
            {program.max_referrals_per_user > 0
              ? program.max_referrals_per_user
              : t('loyalty.noCap')}
          </dd>
        </div>
      </dl>

      <section className="loyalty-program__targeting">
        <h4>{t('loyalty.targeting')}</h4>
        {program.account_types.length > 0 ? (
          <div className="loyalty-chips">
            {program.account_types.map((value) => (
              <Badge key={value} tone="info">
                {options.data?.account_types.find((row) => row.value === value)?.label ?? value}
              </Badge>
            ))}
          </div>
        ) : (
          <p className="muted">{t('loyalty.everyone')}</p>
        )}
      </section>

      {editing ? (
        <form
          className="loyalty-program__form"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate(
              {
                id: program.id,
                name_ar: draft.name_ar,
                name_en: draft.name_en,
                account_types: draft.account_types,
                referrer_points: draft.referrer_points,
                referee_points: draft.referee_points,
                max_referrals_per_user: draft.max_referrals_per_user,
                min_order_amount: draft.min_order_amount,
              },
              {
                onSuccess: () => {
                  notify(t('loyalty.saved'), 'success');
                  setEditing(false);
                },
                onError: fail,
              },
            );
          }}
        >
          <div className="loyalty-grid">
            <label>
              {t('loyalty.nameAr')}
              <input
                required
                value={draft.name_ar}
                onChange={(event) => setDraft({ ...draft, name_ar: event.target.value })}
              />
            </label>

            <label>
              {t('loyalty.nameEn')}
              <input
                dir="ltr"
                required
                value={draft.name_en}
                onChange={(event) => setDraft({ ...draft, name_en: event.target.value })}
              />
            </label>

            <label>
              {t('loyalty.referrerPoints')}
              <input
                type="number"
                min="0"
                dir="ltr"
                value={draft.referrer_points}
                onChange={(event) =>
                  setDraft({ ...draft, referrer_points: Number(event.target.value) })
                }
              />
            </label>

            <label>
              {t('loyalty.refereePoints')}
              <input
                type="number"
                min="0"
                dir="ltr"
                value={draft.referee_points}
                onChange={(event) =>
                  setDraft({ ...draft, referee_points: Number(event.target.value) })
                }
              />
            </label>

            <label>
              {t('loyalty.minOrder')}
              <input
                type="number"
                min="0"
                step="0.01"
                dir="ltr"
                value={draft.min_order_amount}
                onChange={(event) => setDraft({ ...draft, min_order_amount: event.target.value })}
              />
            </label>

            {/* ⚠️  السقف صفر = بلا سقف، ويُقال في التلميح: الحقل
                الفارغ المعنى يجعل الأدمن يكتب رقمًا كبيرًا ظنًّا
                منه أنه يفتح الباب. */}
            <label>
              {t('loyalty.referralCap')}
              <input
                type="number"
                min="0"
                dir="ltr"
                value={draft.max_referrals_per_user}
                onChange={(event) =>
                  setDraft({ ...draft, max_referrals_per_user: Number(event.target.value) })
                }
              />
              <small>{t('loyalty.zeroMeansNoCap')}</small>
            </label>
          </div>

          <fieldset>
            <legend>{t('loyalty.accountTypes')}</legend>
            <p className="muted">{t('loyalty.emptyMeansAll')}</p>
            <div className="loyalty-options">
              {options.data?.account_types.map((row) => (
                <label key={row.value}>
                  <input
                    type="checkbox"
                    checked={draft.account_types.includes(row.value)}
                    onChange={() =>
                      setDraft({
                        ...draft,
                        account_types: flip(draft.account_types, row.value),
                      })
                    }
                  />
                  {row.label}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="loyalty-program__actions">
            <Button type="submit" loading={save.isPending}>
              {t('common.save')}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      ) : (
        <div className="loyalty-program__actions">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setDraft(program);
              setEditing(true);
            }}
          >
            {t('loyalty.editRules')}
          </Button>

          <Button
            size="sm"
            variant="ghost"
            loading={remove.isPending}
            onClick={() => {
              if (!window.confirm(t('loyalty.confirmDeleteProgram'))) return;
              remove.mutate(program.id, {
                onSuccess: () => notify(t('loyalty.deleted'), 'success'),
                onError: fail,
              });
            }}
          >
            {t('common.delete')}
          </Button>
        </div>
      )}
    </article>
  );
}
