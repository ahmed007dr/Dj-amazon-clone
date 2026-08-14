import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { AuthProvider } from '@/features/auth/AuthProvider';
import { useDirection } from '@/shared/i18n/useDirection';
import { ThemeProvider } from '@/shared/theme';

import { queryClient } from './queryClient';

/**
 * ⚠️  الترتيب مقصود:
 *
 *         QueryClient  →  الجميع يجلب عبره
 *         Auth         →  يحقن معالج التجديد في طبقة النقل
 *                          قبل أن يُطلق أي مكوّن نداءً محميًّا
 *         Theme        →  الهوية نداء عام لا يحتاج مصادقة
 *         Direction    →  يضبط `dir` قبل أول رسمة مرئية
 *
 *     عكس Auth وTheme غير ضار اليوم، لكن أول نداء محمي في الثيم
 *     (هوية خاصة بالمستخدم مثلًا) سيمرّ بلا توكن — والفشل حينها
 *     يبدو خطأ صلاحيات لا خطأ ترتيب.
 */
function DirectionGate({ children }: { children: ReactNode }) {
  useDirection();
  return children;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ThemeProvider>
          <DirectionGate>{children}</DirectionGate>
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
