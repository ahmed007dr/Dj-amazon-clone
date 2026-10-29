import { expect, test, type Page } from '@playwright/test';

/**
 * Phone layout regression.
 *
 * ⚠️  Guards a bug that only shows on a real phone width: the store header needed 467px, so
 *     the grid track under it grew to 467px and the whole page became pannable sideways. On
 *     a mobile browser that also widens the layout viewport (`innerWidth` read 467 on a 393px
 *     screen), which dragged every `position: fixed` bar out of line — and on a dark phone
 *     with the light theme the `html` canvas showed through as a black strip beside the page.
 *
 *     The measurement that catches it is `innerWidth`, not `scrollWidth` alone: on a mobile
 *     viewport the two grow together, so only the comparison with the device width is honest.
 */
const PHONES = [360, 393, 430];

/**
 * The dev server mounts the app at `/static/` while the router has no basename, so the first
 * load lands on the not-found page; routing from inside the app is what opens a real route.
 */
async function openRoute(page: Page, path: string) {
  await page.goto('./');
  await page.evaluate((target) => {
    history.pushState(null, '', target);
    dispatchEvent(new PopStateEvent('popstate'));
  }, path);
}

for (const width of PHONES) {
  test.describe(`phone ${String(width)}px`, () => {
    // A dark phone with the app on its light theme — the combination that exposed the strip
    test.use({
      viewport: { width, height: 852 },
      isMobile: true,
      hasTouch: true,
      colorScheme: 'dark',
      locale: 'ar',
    });

    test.beforeEach(async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('theme-preference', 'LIGHT');
      });
    });

    test('the store never scrolls sideways', async ({ page }) => {
      for (const path of ['/products', '/cart']) {
        await openRoute(page, path);
        await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');

        const metrics = await page.evaluate(() => ({
          layoutWidth: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
        }));

        expect(metrics.layoutWidth, `${path}: layout viewport widened`).toBe(width);
        expect(metrics.scrollWidth, `${path}: page wider than the screen`).toBeLessThanOrEqual(width);
      }
    });

    test('the canvas follows the app theme, not the device theme', async ({ page }) => {
      await openRoute(page, '/products');
      await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');

      const colours = await page.evaluate(() => ({
        canvas: getComputedStyle(document.documentElement).backgroundColor,
        body: getComputedStyle(document.body).backgroundColor,
      }));

      expect(colours.canvas).toBe(colours.body);
    });
  });
}
