import type { Page } from '@playwright/test';

import { expect, settle, test } from './fixtures';

/**
 * Smoke test for the in-app guide (`/admin/docs`).
 *
 * ⚠️  Reaches the guide the way an admin does — account menu, then the sidebar link — rather
 *     than `page.goto('/admin/docs')`: the dev server mounts the app under `/static/` while the
 *     router has no basename, so a direct load of a deep path lands on the not-found page.
 *
 * ⚠️  The labels are matched in English (the browser's default here, like every other spec);
 *     the guide's own content is Arabic-only, so the content assertions use structure and one
 *     Arabic search word, never an exact title.
 */
async function openGuideFromSidebar(page: Page) {
  await page.locator('.account-menu__trigger').click();
  await settle(page);
  await page.getByRole('menuitem', { name: /admin/i }).click();
  await page.waitForLoadState('networkidle');
  await settle(page);

  await page.getByRole('link', { name: /guide & help/i }).click();
  await page.waitForLoadState('networkidle');
  await settle(page);
}

test.describe('In-app guide', () => {
  test('sidebar link opens the guide; a topic link deep-links and scrolls to the topic', async ({
    ownerPage: page,
  }) => {
    await openGuideFromSidebar(page);
    await expect(page.getByRole('heading', { level: 1, name: /guide & help/i })).toBeVisible();

    const contents = page.getByRole('navigation', { name: /guide contents/i });
    await contents.locator('.docs-nav__section-link').first().click();
    await expect(page).toHaveURL(/\/admin\/docs\/[\w-]+$/);
    await expect(page.locator('.docs-topic').first()).toBeVisible();

    // A topic link: the URL gets `#<topic id>` and that topic is brought into view (the
    // browser cannot do it itself — the element did not exist when the URL changed).
    await contents.locator('.docs-nav__topic').first().click();
    await expect(page).toHaveURL(/\/admin\/docs\/[\w-]+#[\w-]+$/);
    const topicId = new URL(page.url()).hash.slice(1);
    await expect(page.locator(`#doc-${topicId}`)).toBeInViewport();
  });

  test('a problem opens from the keyboard, and search finds a topic', async ({
    ownerPage: page,
  }) => {
    await openGuideFromSidebar(page);
    await page.locator('.docs-nav__section-link').first().click();
    await settle(page);

    const problem = page.locator('.docs-problem__trigger').first();
    await expect(problem).toHaveAttribute('aria-expanded', 'false');
    await problem.focus();
    await page.keyboard.press('Enter');
    await expect(problem).toHaveAttribute('aria-expanded', 'true');

    // "منتج" = "product" — the one word every catalogue-related topic contains.
    const search = page.getByRole('searchbox', { name: /search the guide/i });
    await search.fill('منتج');
    await expect(page.locator('.docs-result').first()).toBeVisible();

    // Picking a result clears the box and shows the article again.
    await page.locator('.docs-result__title').first().click();
    await expect(search).toHaveValue('');
    await expect(page.locator('.docs-topic').first()).toBeVisible();
  });

  test('the header link on a documented screen opens its topic', async ({ ownerPage: page }) => {
    await page.locator('.account-menu__trigger').click();
    await settle(page);
    await page.getByRole('menuitem', { name: /admin/i }).click();
    await page.waitForLoadState('networkidle');
    await settle(page);

    await page.getByRole('link', { name: /^products$/i }).click();
    await page.waitForLoadState('networkidle');
    await settle(page);

    await page.getByRole('link', { name: /about this page/i }).click();
    await expect(page).toHaveURL(/\/admin\/docs\/[\w-]+#[\w-]+$/);
    await expect(page.locator('.docs-topic').first()).toBeVisible();
  });
});
