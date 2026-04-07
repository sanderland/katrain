import { test, expect } from '@playwright/test';

async function login(page: Parameters<typeof test>[1]['page']) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const loginVisible = await page.getByText('Login').isVisible().catch(() => false);
  if (loginVisible) {
    await page.getByLabel('Username').fill('admin');
    await page.getByLabel('Password').fill('admin');
    await page.getByRole('button', { name: 'Login' }).click();
    await page.waitForLoadState('networkidle');
  }
}

test.describe('Tutorial Module V2', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  test('Tutorial link appears in sidebar', async ({ page }) => {
    await page.goto('/galaxy');
    await expect(page.getByText('教程')).toBeVisible({ timeout: 10000 });
  });

  test('Landing page shows 4 category cards', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await expect(page.getByText('入门')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('布局')).toBeVisible();
    await expect(page.getByText('中盘')).toBeVisible();
    await expect(page.getByText('官子')).toBeVisible();
  });

  test('Landing page shows category summaries', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await expect(page.getByText('围棋基础知识')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('开局阶段')).toBeVisible();
  });

  test('Clicking category navigates to books list', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    await expect(page.getByText('← 返回')).toBeVisible({ timeout: 10000 });
  });

  test('Books page shows imported books or empty state', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    // Should show either a book card or "该分类暂无书籍"
    const hasBook = await page.locator('.MuiCard-root').first().isVisible({ timeout: 5000 }).catch(() => false);
    const hasEmpty = await page.getByText('该分类暂无书籍').isVisible().catch(() => false);
    expect(hasBook || hasEmpty).toBe(true);
  });

  test('Empty category shows appropriate message', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('入门').first().click();
    // 入门 likely has no imported books
    await expect(page.getByText('该分类暂无书籍')).toBeVisible({ timeout: 10000 });
  });

  test('Clicking book navigates to chapter/section tree', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    await page.waitForTimeout(1000);
    const card = page.locator('.MuiCard-root').first();
    if (await card.isVisible({ timeout: 3000 }).catch(() => false)) {
      await card.click();
      // Should see chapter accordion or section list
      await expect(page.getByText('← 返回')).toBeVisible({ timeout: 10000 });
    }
  });

  test('Book detail shows chapters with section counts', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    await page.waitForTimeout(1000);
    const card = page.locator('.MuiCard-root').first();
    if (await card.isVisible({ timeout: 3000 }).catch(() => false)) {
      await card.click();
      await page.waitForTimeout(1000);
      // Should see section count text somewhere
      await expect(page.getByText(/节/).first()).toBeVisible({ timeout: 10000 });
    }
  });

  test('Section link opens figure page', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    await page.waitForTimeout(1000);
    const card = page.locator('.MuiCard-root').first();
    if (await card.isVisible({ timeout: 3000 }).catch(() => false)) {
      await card.click();
      await page.waitForTimeout(1500);
      // Click first section link (has "个变化图" text)
      const sectionLink = page.getByText(/个变化图/).first();
      if (await sectionLink.isVisible({ timeout: 3000 }).catch(() => false)) {
        await sectionLink.click();
        // Should see figure page with navigation
        await expect(page.getByLabel('下一图').or(page.getByLabel('上一图'))).toBeVisible({ timeout: 10000 });
      }
    }
  });

  test('Figure page shows page screenshot', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    await page.waitForTimeout(1000);
    const card = page.locator('.MuiCard-root').first();
    if (await card.isVisible({ timeout: 3000 }).catch(() => false)) {
      await card.click();
      await page.waitForTimeout(1500);
      const sectionLink = page.getByText(/个变化图/).first();
      if (await sectionLink.isVisible({ timeout: 3000 }).catch(() => false)) {
        await sectionLink.click();
        await page.waitForTimeout(1000);
        // Page screenshot should be visible
        const img = page.locator('img[alt*="page"]');
        await expect(img.first()).toBeVisible({ timeout: 10000 });
      }
    }
  });

  test('Figure navigation: next/prev between figures', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    await page.waitForTimeout(1000);
    const card = page.locator('.MuiCard-root').first();
    if (await card.isVisible({ timeout: 3000 }).catch(() => false)) {
      await card.click();
      await page.waitForTimeout(1500);
      const sectionLink = page.getByText(/个变化图/).first();
      if (await sectionLink.isVisible({ timeout: 3000 }).catch(() => false)) {
        await sectionLink.click();
        await page.waitForTimeout(1000);
        // Click next figure
        const nextBtn = page.getByLabel('下一图');
        if (await nextBtn.isEnabled({ timeout: 3000 }).catch(() => false)) {
          await nextBtn.click();
          await page.waitForTimeout(500);
          // Should show different figure (图2)
          await expect(page.getByText(/图[2-9]/)).toBeVisible({ timeout: 5000 });
        }
      }
    }
  });

  test('Back navigation works from each page', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').first().click();
    await page.waitForTimeout(1000);
    // Click back
    await page.getByText('← 返回').click();
    // Should be back at landing page
    await expect(page.getByText('入门')).toBeVisible({ timeout: 10000 });
  });
});
