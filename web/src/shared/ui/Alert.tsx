import type { ReactNode } from 'react';

import './Alert.css';

type Tone = 'info' | 'success' | 'warning' | 'danger';

/**
 * ⚠️  `role="alert"` للخطأ فقط.
 *
 *     يقاطع قارئ الشاشة فورًا — مناسب لفشل تسجيل دخول، ومزعج
 *     لرسالة معلوماتية تُقرأ فوق ما كان المستخدم يستمع إليه.
 */
export function Alert({ tone = 'info', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div className={`alert alert--${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}
