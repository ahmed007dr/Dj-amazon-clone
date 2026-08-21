import { createContext } from 'react';

import type { BrandTheme, DefaultMode, ThemeMode } from './types';

export interface ThemeContextValue {
  theme: BrandTheme | null;
  /** The mode actually applied — after `SYSTEM` is resolved. */
  mode: ThemeMode;
  /** The user's choice, which may be `SYSTEM`. */
  preference: DefaultMode;
  setPreference: (next: DefaultMode) => void;
  isLoading: boolean;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);
