import type { ReactNode } from 'react';

import './Badge.css';

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
