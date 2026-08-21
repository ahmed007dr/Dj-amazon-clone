import type { ReactNode } from 'react';

import './Alert.css';

type Tone = 'info' | 'success' | 'warning' | 'danger';

/**
 * ⚠️  `role="alert"` for errors only.
 *
 *     It interrupts the screen reader immediately — appropriate for a failed
 *     sign-in, and irritating for an informational message read over whatever
 *     the user was listening to.
 */
export function Alert({ tone = 'info', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div className={`alert alert--${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}
