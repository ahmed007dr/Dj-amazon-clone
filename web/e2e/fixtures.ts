import { test as base, type Page } from '@playwright/test';

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? 'owner@dev.local';
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? 'Dev-Pass!2026';

async function loginAsOwner(page: Page) {
  await page.goto('/');
  await page.getByText(/sign in/i).first().click();
  await page.waitForLoadState('networkidle');
  await page.getByLabel(/email or phone/i).fill(OWNER_EMAIL);
  await page.getByLabel(/^password$/i).fill(OWNER_PASSWORD);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForTimeout(1500);
}

/**
 * ⚠️  Small settle pauses, not just `waitFor`/`networkidle`: this is
 *     client-side routing, so there's no navigation-level network activity
 *     to wait on for a menu opening or a route swapping in. The occasional
 *     residual race is absorbed by `retries` in playwright.config.ts rather
 *     than chased further here — it's test-environment timing, not the
 *     input-focus behavior under test.
 */
async function settle(page: Page) {
  await page.waitForTimeout(400);
}

async function gotoAdminAcademic(page: Page) {
  await page.locator('.account-menu__trigger').click();
  await settle(page);
  await page.getByRole('menuitem', { name: /admin/i }).click();
  await page.waitForLoadState('networkidle');
  await settle(page);
  // ⚠️  The sidebar link is "Academic & student requests" (it was "Academic tree"),
  //     and may carry a pending-count badge after the label — hence no end anchor.
  await page.getByRole('link', { name: /academic & student requests/i }).click();
  await page.waitForLoadState('networkidle');
  await settle(page);

  // ⚠️  The page opens on "Verification requests" now, not "Universities".
  //     Every spec in focus-retention.spec.ts assumes the tree tabs, so land on the
  //     first of them explicitly instead of relying on whichever tab is the default.
  await page.getByRole('tab', { name: /verification requests/i }).waitFor();
  await page.getByRole('tab', { name: /universities/i }).click();
  await settle(page);
  await page.getByRole('button', { name: /add university/i }).first().waitFor();
}

export const test = base.extend<{ ownerPage: Page }>({
  ownerPage: async ({ page }, use) => {
    await loginAsOwner(page);
    await use(page);
  },
});

export { gotoAdminAcademic, settle };
export { expect } from '@playwright/test';
