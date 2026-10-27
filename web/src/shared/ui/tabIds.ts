/**
 * The DOM ids that tie a tab to its panel.
 *
 * ⚠️  One definition for both sides.
 *
 *     `StatusTabs` writes `aria-controls` and `TabPanel` writes `id`; if each
 *     built the string on its own, a one-character drift would leave the tab
 *     pointing at nothing and no test would notice — screen readers just stop
 *     announcing "tab 2 of 3, controls panel".
 */
const safe = (value: string) => value.replace(/\s+/g, '-');

export const tabDomId = (base: string, value: string) => `${base}-tab-${safe(value)}`;

export const panelDomId = (base: string, value: string) => `${base}-panel-${safe(value)}`;
