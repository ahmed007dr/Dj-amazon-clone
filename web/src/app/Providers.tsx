import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { useDirection } from '@/shared/i18n/useDirection';
import { ThemeProvider } from '@/shared/theme';

import { queryClient } from './queryClient';

/**
 * ⚠️  الترتيب مقصود:
 *
 *         QueryClient  →  ThemeProvider يجلب الهوية عبره
 *         Direction    →  يضبط `dir` قبل أول رسمة مرئية
 *
 *     عكسه يجعل `ThemeProvider` بلا عميل جلب، والصفحة تومض بتخطيط
 *     إنجليزي قبل أن تنقلب إلى العربية.
 */
function DirectionGate({ children }: { children: ReactNode }) {
  useDirection();
  return children;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DirectionGate>{children}</DirectionGate>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
