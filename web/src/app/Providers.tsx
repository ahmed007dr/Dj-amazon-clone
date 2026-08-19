import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { AuthProvider } from '@/features/auth/AuthProvider';
import { useDirection } from '@/shared/i18n/useDirection';
import { ThemeProvider } from '@/shared/theme';
import { ToastProvider } from '@/shared/ui/ToastProvider';

import { queryClient } from './queryClient';

/**
 * ⚠️  The order is deliberate:
 *
 *         QueryClient  →  everyone fetches through it
 *         Auth         →  injects the refresh handler into the transport layer
 *                          before any component fires a protected call
 *         Theme        →  branding is a public call needing no authentication
 *         Direction    →  sets `dir` before the first visible render
 *
 *     Swapping Auth and Theme is harmless today, but the first protected call
 *     in the theme (per-user branding, say) would go out without a token — and
 *     the failure would look like a permissions bug rather than an ordering one.
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
          <ToastProvider>
            <DirectionGate>{children}</DirectionGate>
          </ToastProvider>
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
