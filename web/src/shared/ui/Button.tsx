import type { ButtonHTMLAttributes, ReactNode } from 'react';

import './Button.css';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Fills the container's width — the default on a phone in forms. */
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
      // ⚠️  Disabling while loading prevents a double submission — which is what
      //     produces two identical requests when the network is slow and the user clicks again.
      disabled={disabled ?? loading}
      aria-busy={loading}
      {...rest}
    >
      {loading ? <span className="btn__spinner" aria-hidden /> : icon}
      {children}
    </button>
  );
}
