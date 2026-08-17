import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteProgram,
  useSaveProgram,
  useTargetingOptions,
  type LoyaltyProgram,
} from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';
import { TierEditor } from '@/portals/admin/components/TierEditor';

import './LoyaltyProgramCard.css';

/**
 * بطاقة برنامج ولاء — **المفتاح والاستهداف**.
 *
 * ⚠️  **المفتاح في أعلى البطاقة لا داخل نموذج التعديل.**
 *
 *     إيقاف البرنامج قرار يُتخذ فجأة (شكوى · مراجعة التزام ·
 *     خطأ في الضبط). دفنه خلف «تعديل ← حفظ» يجعل الأدمن يبحث عنه
 *     دقائق بينما النظام يستمر في منح النقاط.
 *
 * ⚠️  و**الاستهداف يقول من يشمله بالكلمات لا بالأكواد**.
 *
 *     `["PHARMACY","WAREHOUSE"]` في حقل نصي يجعل خطأ إملائيًا
 *     واحدًا يُنتج برنامجًا مفعَّلًا لا يكسب فيه أحد — وهو عطل
 *     صامت لا رسالة له. الاختيار من قائمة يمنعه من الأساس.
 */
export function LoyaltyProgramCard({ program }: { program: LoyaltyProgram }) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const options = useTargetingOptions();
  const save = useSaveProgram();
  const remove = useDeleteProgram();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(program);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const toggle = (patch: Partial<LoyaltyProgram>) =>
    save.mutate(
      { id: program.id, ...patch },
      {
        onSuccess: () => notify(t('loyalty.saved'), 'success'),
        onError: fail,
      },
    );

  const submit = () =>
    save.mutate(
      {
        id: program.id,
        name_ar: draft.name_ar,
        name_en: draft.name_en,
        note: draft.note,
        account_types: draft.account_types,
        customer_segments: draft.customer_segments,
        currency_per_point: draft.currency_per_point,
        point_value: draft.point_value,
        min_order_amount: draft.min_order_amount,
        max_redemption_percent: draft.max_redemption_percent,
        expiry_months: draft.expiry_months,
        earns_on_tax: draft.earns_on_tax,
        earns_on_shipping: draft.earns_on_shipping,
        reverse_on_refund: draft.reverse_on_refund,
      },
      {
        onSuccess: () => {
          notify(t('loyalty.saved'), 'success');
          setEditing(false);
        },
        onError: fail,
      },
    );

  const flip = (list: string[], value: string) =>
    list.includes(value) ? list.filter((row) => row !== value) : [...list, value];

  const targeted = program.account_types.length > 0 || program.customer_segments.length > 0;

  return (
    <article className={`loyalty-program surface ${program.is_active ? 'is-on' : 'is-off'}`}>
      <header className="loyalty-program__head">
        <div>
          <h3>{localized(program, 'name')}</h3>
          <code dir="ltr">{program.code}</code>
        </div>

        {/* ⚠️  المفتاح أول ما تراه العين وآخر ما تحتاج البحث عنه */}
        <label className="loyalty-switch">
          <input
            type="checkbox"
            checked={program.is_active}
            disabled={save.isPending}
            onChange={(event) => toggle({ is_active: event.target.checked })}
          />
          <span className="loyalty-switch__track" aria-hidden />
          <span className="loyalty-switch__text">
            {program.is_active ? t('loyalty.on') : t('loyalty.off')}
          </span>
        </label>
      </header>

      {/* ⚠️  الإيقاف **لا يمحو الأرصدة** — قوله صراحةً يمنع
          السؤال الذي يأتي بعد أول إيقاف. */}
      {!program.is_active ? (
        <Alert tone="info">{t('loyalty.offNotice')}</Alert>
      ) : null}

      <dl className="loyalty-program__facts">
        <div>
          <dt>{t('loyalty.earnRate')}</dt>
          <dd dir="ltr">
            {program.currency_per_point} → 1 {t('loyalty.point')}
          </dd>
        </div>
        <div>
          <dt>{t('loyalty.pointValue')}</dt>
          <dd dir="ltr">{program.point_value}</dd>
        </div>
        <div>
          <dt>{t('loyalty.maxRedemption')}</dt>
          <dd dir="ltr">{program.max_redemption_percent}%</dd>
        </div>
        <div>
          <dt>{t('loyalty.expiry')}</dt>
          <dd>
            {program.expiry_months > 0
              ? t('loyalty.months', { count: program.expiry_months })
              : t('loyalty.noExpiry')}
          </dd>
        </div>
      </dl>

      <section className="loyalty-program__targeting">
        <h4>{t('loyalty.targeting')}</h4>

        {targeted ? (
          <div className="loyalty-chips">
            {program.account_types.map((value) => (
              <Badge key={value} tone="info">
                {options.data?.account_types.find((row) => row.value === value)?.label ?? value}
              </Badge>
            ))}
            {program.customer_segments.map((value) => (
              <Badge key={value} tone="neutral">
                {options.data?.customer_segments.find((row) => row.value === value)?.label ?? value}
              </Badge>
            ))}
          </div>
        ) : (
          <p className="muted">{t('loyalty.everyone')}</p>
        )}

        {/* ⚠️  الشرطان يُطبَّقان **معًا**: «صيدليات مميّزة» لا «كل
            صيدلية أو كل مميّز». قولها هنا يمنع ضبطًا يظن الأدمن
            أنه يوسّع بينما هو يضيّق. */}
        {program.account_types.length > 0 && program.customer_segments.length > 0 ? (
          <p className="loyalty-note">{t('loyalty.bothApply')}</p>
        ) : null}
      </section>

      {editing ? (
        <form
          className="loyalty-program__form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          {/* ⚠️  الاسم يُعدَّل من هنا لا من قاعدة البيانات: حملة
              تُعاد تسميتها موسميًا («نقاط الصيف») ولا يُعقل أن
              تحتاج نشرًا. والرمز ثابت لأنه مرجع الحركات. */}
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
          </div>

          <label className="loyalty-note-field">
            {t('loyalty.internalNote')}
            <textarea
              rows={2}
              value={draft.note}
              onChange={(event) => setDraft({ ...draft, note: event.target.value })}
            />
          </label>

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

          <fieldset>
            <legend>{t('loyalty.segments')}</legend>
            <p className="muted">{t('loyalty.emptyMeansAll')}</p>
            <div className="loyalty-options">
              {options.data?.customer_segments.map((row) => (
                <label key={row.value}>
                  <input
                    type="checkbox"
                    checked={draft.customer_segments.includes(row.value)}
                    onChange={() =>
                      setDraft({
                        ...draft,
                        customer_segments: flip(draft.customer_segments, row.value),
                      })
                    }
                  />
                  {row.label}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="loyalty-grid">
            <label>
              {t('loyalty.currencyPerPoint')}
              <input
                type="number"
                min="1"
                step="0.01"
                dir="ltr"
                value={draft.currency_per_point}
                onChange={(event) =>
                  setDraft({ ...draft, currency_per_point: event.target.value })
                }
              />
            </label>

            <label>
              {t('loyalty.pointValue')}
              <input
                type="number"
                min="0"
                step="0.0001"
                dir="ltr"
                value={draft.point_value}
                onChange={(event) => setDraft({ ...draft, point_value: event.target.value })}
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

            <label>
              {t('loyalty.maxRedemption')}
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                dir="ltr"
                value={draft.max_redemption_percent}
                onChange={(event) =>
                  setDraft({ ...draft, max_redemption_percent: event.target.value })
                }
              />
            </label>

            <label>
              {t('loyalty.expiryMonths')}
              <input
                type="number"
                min="0"
                dir="ltr"
                value={draft.expiry_months}
                onChange={(event) =>
                  setDraft({ ...draft, expiry_months: Number(event.target.value) })
                }
              />
            </label>
          </div>

          <div className="loyalty-toggles">
            <label>
              <input
                type="checkbox"
                checked={draft.earns_on_tax}
                onChange={(event) => setDraft({ ...draft, earns_on_tax: event.target.checked })}
              />
              {t('loyalty.earnsOnTax')}
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.earns_on_shipping}
                onChange={(event) =>
                  setDraft({ ...draft, earns_on_shipping: event.target.checked })
                }
              />
              {t('loyalty.earnsOnShipping')}
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.reverse_on_refund}
                onChange={(event) =>
                  setDraft({ ...draft, reverse_on_refund: event.target.checked })
                }
              />
              {t('loyalty.reverseOnRefund')}
            </label>
          </div>

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

          {/* ⚠️  مفتاحان لا واحد: إيقاف الصرف مع استمرار الكسب
              موقف تشغيلي حقيقي عند مراجعة الالتزام. */}
          <Button
            size="sm"
            variant="ghost"
            loading={save.isPending}
            onClick={() => toggle({ redemption_enabled: !program.redemption_enabled })}
          >
            {program.redemption_enabled
              ? t('loyalty.pauseRedemption')
              : t('loyalty.resumeRedemption')}
          </Button>

          {/* ⚠️  الحذف آخر الصف ويسأل أولًا؛ والخادم يرفضه أصلًا
              لو مُنحت منه نقطة واحدة — والرسالة تقول «أوقفه». */}
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

      <TierEditor programId={program.id} tiers={program.tiers} />
    </article>
  );
}
