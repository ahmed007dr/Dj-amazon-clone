import { useId, type InputHTMLAttributes } from 'react';

import './Field.css';

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string | undefined;
  hint?: string | undefined;
}

/**
 * حقل إدخال بتسمية وخطأ مرتبطين.
 *
 * ⚠️  `useId` لا رقم عشوائي ولا اسم الحقل.
 *
 *     التسمية غير المرتبطة تجعل النقر عليها لا يركّز الحقل، وقارئ
 *     الشاشة يقرأ «حقل نصي» بلا اسم. و`aria-describedby` هو ما
 *     يجعله ينطق رسالة الخطأ بدل أن تبقى نصًّا أحمر لا يراه.
 */
export function Field({ label, error, hint, id, ...rest }: Props) {
  const generated = useId();
  const inputId = id ?? generated;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;

  const describedBy = [error ? errorId : null, hint ? hintId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="field">
      <label className="field__label" htmlFor={inputId}>
        {label}
      </label>

      <input
        id={inputId}
        className={`field__input ${error ? 'has-error' : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        {...rest}
      />

      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}

      {error ? (
        <p id={errorId} className="field__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
