/**
 * مزوّد الثيم — يجلب الهوية من الخادم ويحقنها.
 *
 * ⚠️  اختيار الوضع محلي، والألوان من الخادم.
 *
 *     الأدمن يملك **اللوحتين**؛ والمستخدم يملك **أيهما يرى**. خلط
 *     الاثنين يعني إما أدمنًا لا يستطيع تغيير الألوان، أو مستخدمًا
 *     لا يستطيع اختيار الوضع الداكن.
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
    // ⚠️  الهوية لا تتغيّر مرة في الشهر — إعادة جلبها عند كل تركيز
    //     نافذة إهدار خالص على بيانات ثابتة.
    staleTime: 30 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const [preference, setPreferenceState] = useState<DefaultMode>(
    () => storedPreference() ?? 'SYSTEM',
  );
  const [system, setSystem] = useState<ThemeMode>(systemMode);

  // اختيار المستخدم يسبق افتراضي الأدمن؛ وافتراضي الأدمن يسبق النظام
  const effectivePreference: DefaultMode =
    storedPreference() ?? theme?.default_mode ?? preference;

  const mode: ThemeMode = effectivePreference === 'SYSTEM' ? system : effectivePreference;

  // ⚠️  تفضيل الجهاز يتغيّر أثناء الجلسة (غروب الشمس على الهاتف).
  //     قراءته مرة عند الإقلاع تترك الصفحة فاتحة بينما صار النظام داكنًا.
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
