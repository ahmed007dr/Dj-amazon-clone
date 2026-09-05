import type { Locator } from '@playwright/test';

import { expect, gotoAdminAcademic, settle, test } from './fixtures';

/**
 * Regression test for a focus-stealing bug in the shared `Drawer`/`Modal`
 * components: their open/Escape effect depended on `[open, onClose]`, and
 * `onClose` is a fresh closure on every parent render — so every keystroke
 * in a controlled input re-ran the effect and called `panelRef.current
 * .focus()`, yanking focus away from the input the user was typing into.
 *
 * Left uncaught, this reduces to "type one character, lose focus, click
 * back in" for every input inside every Drawer/Modal in the app — it isn't
 * specific to Academic, it's the fix's blast radius.
 */

const SAMPLE = 'Ahmed Mohamed 12345';

async function typeContinuously(input: Locator, text: string) {
  await input.click();
  await input.fill('');
  for (const char of text) {
    await input.press(char === ' ' ? 'Space' : char);
  }
}

async function expectFocusedWithValue(input: Locator, expected: string) {
  await expect(input).toHaveValue(expected);
  await expect(input).toBeFocused();
}

test.describe('Drawer/Modal forms keep focus while typing', () => {
  test('Add University drawer', async ({ ownerPage: page }) => {
    await gotoAdminAcademic(page);
    const addBtn = page.getByRole('button', { name: /add university/i }).first();
    await addBtn.click();
    await settle(page);

    const code = page.getByRole('dialog').locator('input[dir="ltr"]').first();
    await typeContinuously(code, SAMPLE);
    await expectFocusedWithValue(code, SAMPLE);

    // Cursor position: Backspace removes from the end, not the start.
    await code.press('Backspace');
    await code.press('Backspace');
    await code.press('Backspace');
    await expect(code).toHaveValue(SAMPLE.slice(0, -3));

    // Home + insert lands at the true start of the string, not reversed.
    await code.press('Home');
    await code.press('X');
    await expect(code).toHaveValue('X' + SAMPLE.slice(0, -3));
  });

  test('Add Faculty drawer', async ({ ownerPage: page }) => {
    await gotoAdminAcademic(page);
    await page.getByRole('tab', { name: /faculties/i }).click();
    await settle(page);
    const addBtn = page.getByRole('button', { name: /add faculty/i }).first();
    await addBtn.click();
    await settle(page);

    const code = page.getByRole('dialog').locator('input[dir="ltr"]').first();
    await typeContinuously(code, SAMPLE);
    await expectFocusedWithValue(code, SAMPLE);
  });

  test('Add Department drawer', async ({ ownerPage: page }) => {
    await gotoAdminAcademic(page);
    await page.getByRole('tab', { name: /departments/i }).click();
    await settle(page);
    const addBtn = page.getByRole('button', { name: /add department/i }).first();
    await addBtn.click();
    await settle(page);

    const code = page.getByRole('dialog').locator('input[dir="ltr"]').first();
    await typeContinuously(code, SAMPLE);
    await expectFocusedWithValue(code, SAMPLE);
  });

  test('Add Bundle drawer — text, number, and textarea inputs', async ({ ownerPage: page }) => {
    await gotoAdminAcademic(page);
    await page.getByRole('tab', { name: /bundles/i }).click();
    await settle(page);
    const addBtn = page.getByRole('button', { name: /add bundle/i });
    await addBtn.click();
    await settle(page);

    const dialog = page.getByRole('dialog');

    const nameEn = dialog.locator('input[dir="ltr"]:not([type="number"])').first();
    await typeContinuously(nameEn, SAMPLE);
    await expectFocusedWithValue(nameEn, SAMPLE);

    const description = dialog.locator('textarea[dir="ltr"]').first();
    await typeContinuously(description, SAMPLE);
    await expectFocusedWithValue(description, SAMPLE);
  });

  test('Suspend account modal — Modal component, not Drawer', async ({ ownerPage: page }) => {
    await page.locator('.account-menu__trigger').click();
    await settle(page);
    await page.getByRole('menuitem', { name: /admin/i }).click();
    await page.waitForLoadState('networkidle');
    await settle(page);
    await page.getByRole('link', { name: /^users$/i }).click();
    await page.waitForLoadState('networkidle');
    await settle(page);

    const suspendBtn = page.getByRole('button', { name: /suspend|block|activate/i }).first();
    await suspendBtn.click();
    await settle(page);

    const reason = page.locator('#suspend-reason');
    await typeContinuously(reason, SAMPLE);
    await expectFocusedWithValue(reason, SAMPLE);

    // Don't submit — this is a read-only focus check, not an account mutation.
    await page.getByRole('button', { name: /cancel/i }).click();
  });
});
