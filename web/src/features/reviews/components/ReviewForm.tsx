import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCreateReview,
  useDeleteReview,
  useUpdateReview,
  type MyReview,
} from '@/features/reviews/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './ReviewForm.css';

/**
 * كتابة تقييم أو تعديله.
 *
 * ⚠️  **النجوم مُدخل لا زخرفة**: أزرار اختيار حقيقية بلوحة المفاتيح.
 *
 *     النجمة صورةً تُنقَر لا يصلها مستخدم لوحة المفاتيح ولا قارئ
 *     الشاشة — والتقييم هو الحقل **الوحيد الإلزامي** في النموذج.
 *
 * ⚠️  و**التقييم يبدأ معلّقًا دائمًا** — يقال صراحةً بعد الإرسال.
 *
 *     المستخدم يبحث عن تقييمه في الصفحة فلا يجده (القائمة تعرض
 *     المعتمد وحده) فيعيد كتابته، فيصطدم بـ«لديك تقييم بالفعل».
 */
export function ReviewForm({
  productId,
  existing,
  onDone,
}: {
  productId: string;
  existing?: MyReview | undefined;
  onDone?: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const create = useCreateReview();
  const update = useUpdateReview();
  const remove = useDeleteReview();

  const [rating, setRating] = useState(existing?.rating ?? 0);
  const [title, setTitle] = useState(existing?.title ?? '');
  const [body, setBody] = useState(existing?.body ?? '');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const busy = create.isPending || update.isPending || remove.isPending;

  const onError = (error: unknown) => {
    if (isApiError(error)) {
      const next: Record<string, string> = {};
      for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
      setFieldErrors(next);
      notify(error.displayMessage, 'danger');
      return;
    }
    notify(t('state.errorTitle'), 'danger');
  };

  const submit = () => {
    setFieldErrors({});

    if (existing) {
      update.mutate(
        { id: existing.id, body: { rating, title, body } },
        {
          onSuccess: () => {
            notify(t('reviews.updatedPending'), 'success');
            onDone?.();
          },
          onError,
        },
      );
      return;
    }

    create.mutate(
      { product: productId, rating, title, body },
      {
        onSuccess: () => {
          notify(t('reviews.submittedPending'), 'success');
          onDone?.();
        },
        onError,
      },
    );
  };

  return (
    <div className="review-form">
      <fieldset className="review-form__stars">
        <legend>
          {t('reviews.yourRating')}
          <em aria-hidden> *</em>
        </legend>

        {/* ⚠️  من الأعلى إلى الأدنى في DOM ليصحّ الاتجاه بصريًا في
            RTL دون قلب معنى «خمس نجوم». */}
        {[5, 4, 3, 2, 1].map((value) => (
          <label key={value} className={value <= rating ? 'is-on' : ''}>
            <input
              type="radio"
              name="rating"
              value={value}
              checked={rating === value}
              onChange={() => setRating(value)}
            />
            <span aria-hidden>★</span>
            <span className="review-form__sr">{t('reviews.starsCount', { count: value })}</span>
          </label>
        ))}
      </fieldset>

      {fieldErrors.rating ? <Alert tone="danger">{fieldErrors.rating}</Alert> : null}

      <Field
        label={t('reviews.title')}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        maxLength={200}
        {...(fieldErrors.title ? { error: fieldErrors.title } : {})}
      />

      <label className="review-form__body">
        <span>{t('reviews.body')}</span>
        <textarea
          rows={5}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder={t('reviews.bodyPlaceholder')}
        />
        {fieldErrors.body ? (
          <span className="review-form__error" role="alert">
            {fieldErrors.body}
          </span>
        ) : null}
      </label>

      {/* ⚠️  تعديل تقييم منشور يعيده إلى المراجعة — يُقال قبل الحفظ
          لا بعده، وإلا فوجئ المستخدم باختفاء تقييمه من الصفحة. */}
      <Alert tone="info">
        {existing ? t('reviews.editReturnsToReview') : t('reviews.pendingNotice')}
      </Alert>

      <div className="review-form__actions">
        <Button onClick={submit} loading={busy} disabled={rating === 0}>
          {existing ? t('common.save') : t('reviews.submit')}
        </Button>

        {existing ? (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() =>
              remove.mutate(existing.id, {
                onSuccess: () => {
                  notify(t('reviews.deleted'), 'success');
                  onDone?.();
                },
                onError,
              })
            }
          >
            {t('common.delete')}
          </Button>
        ) : null}

        {onDone ? (
          <Button variant="ghost" onClick={onDone} disabled={busy}>
            {t('common.cancel')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
