/**
 * The theme provider — it fetches the identity from the server and injects it.
 *
 * ⚠️  The mode choice is local, and the colours come from the server.
 *
 *     The admin owns **both palettes**; the user owns **which of them they see**.
 *     Mixing the two means either an admin who cannot change the colours, or a
 *     user who cannot choose dark mode.
 */

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { getTheme } from '@/features/branding/api';

import { applyFavicon, applyTheme } from './applyTheme';
import { ThemeContext, type ThemeContextValue } from './ThemeContext';
import type { DefaultMode, ThemeMode } from './types';

const STORAGE_KEY = 'theme-preference';

function storedPreference(): DefaultMode | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === 'LIGHT' || value === 'DARK' || value === 'SYSTEM' ? value : null;
}

function systemMode(): ThemeMode {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'DARK' : 'LIGHT';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { data: theme, isLoading } = useQuery({
    queryKey: ['branding', 'theme'],
    queryFn: getTheme,
    // ⚠️  The identity does not change once a month — refetching it on every window
    //     focus is pure waste on static data.
    staleTime: 30 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const [preference, setPreferenceState] = useState<DefaultMode>(
    () => storedPreference() ?? 'SYSTEM',
  );
  const [system, setSystem] = useState<ThemeMode>(systemMode);

  // The user's choice takes precedence over the admin's default; and the admin's default over the system
  const effectivePreference: DefaultMode =
    storedPreference() ?? theme?.default_mode ?? preference;

  const mode: ThemeMode = effectivePreference === 'SYSTEM' ? system : effectivePreference;

  // ⚠️  The device preference changes during a session (sunset, on a phone).
  //     Reading it once at boot leaves the page light while the system has gone dark.
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (event: MediaQueryListEvent) => {
      setSystem(event.matches ? 'DARK' : 'LIGHT');
    };
    media.addEventListener('change', onChange);
    return () => {
      media.removeEventListener('change', onChange);
    };
  }, []);

  useEffect(() => {
    if (theme) {
      applyTheme(theme, mode);
      applyFavicon(theme.assets.favicon);
    }
  }, [theme, mode]);

  const setPreference = useCallback((next: DefaultMode) => {
    localStorage.setItem(STORAGE_KEY, next);
    setPreferenceState(next);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme: theme ?? null,
      mode,
      preference: effectivePreference,
      setPreference,
      isLoading,
    }),
    [theme, mode, effectivePreference, setPreference, isLoading],
  );

  return <ThemeContext value={value}>{children}</ThemeContext>;
}
