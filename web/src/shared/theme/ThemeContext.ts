import { createContext } from 'react';

import type { BrandTheme, DefaultMode, ThemeMode } from './types';

export interface ThemeContextValue {
  theme: BrandTheme | null;
  /** الوضع المطبَّق فعليًا — بعد حسم `SYSTEM`. */
  mode: ThemeMode;
  /** اختيار المستخدم، وقد يكون `SYSTEM`. */
  preference: DefaultMode;
  setPreference: (next: DefaultMode) => void;
  isLoading: boolean;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);
