import { useContext } from 'react';

import { ThemeContext, type ThemeContextValue } from './ThemeContext';

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme خارج ThemeProvider');
  }
  return context;
}
