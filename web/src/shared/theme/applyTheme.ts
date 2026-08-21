/**
 * Injecting the theme tokens into the root element.
 *
 * ⚠️  The tokens arrive **ready-made** from the server (`--color-primary: #…`).
 *
 *     Building the token names in the frontend means duplicating them in two
 *     repositories, so adding one colour becomes two edits — and one of them
 *     gets forgotten.
 */

import type { BrandTheme, ThemeMode } from './types';

export function applyTheme(theme: BrandTheme, mode: ThemeMode): void {
  const root = document.documentElement;

  for (const [token, value] of Object.entries(theme.tokens)) {
    root.style.setProperty(token, value);
  }

  for (const [token, value] of Object.entries(theme.palettes[mode] ?? {})) {
    root.style.setProperty(token, value);
  }

  root.dataset.theme = mode === 'DARK' ? 'dark' : 'light';

  // ⚠️  Tells the browser the colour of its native controls (the scrollbar ·
  //     input fields). Without it they stay white inside a dark page.
  root.style.colorScheme = mode === 'DARK' ? 'dark' : 'light';
}

/** Updates the tab icon when the admin uploads a new one. */
export function applyFavicon(href: string): void {
  if (!href) return;

  const link =
    document.querySelector<HTMLLinkElement>("link[rel='icon']") ??
    document.head.appendChild(Object.assign(document.createElement('link'), { rel: 'icon' }));

  link.href = href;
}
