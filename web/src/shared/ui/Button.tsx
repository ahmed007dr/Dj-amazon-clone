import type { ButtonHTMLAttributes, ReactNode } from 'react';

import './Button.css';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** يملأ عرض الحاوية — الافتراضي على الهاتف في النماذج. */
  block?: boolean;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  block = false,
  loading = false,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: Props) {
  return (
    <button
      type="button"
      className={`btn btn--${variant} btn--${size} ${block ? 'btn--block' : ''} ${className}`}
      // ⚠️  التعطيل أثناء التحميل يمنع إرسالًا مزدوجًا — وهو ما
      //     ينتج طلبين متطابقين حين تتأخر الشبكة والمستخدم ينقر ثانيةً.
      disabled={disabled ?? loading}
      aria-busy={loading}
      {...rest}
    >
      {loading ? <span className="btn__spinner" aria-hidden /> : icon}
      {children}
    </button>
  );
}
