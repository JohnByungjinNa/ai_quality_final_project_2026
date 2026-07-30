const { test, expect } = require('@playwright/test');

test('open VOC Agent management and capture readiness', async ({ page }) => {
  await page.goto('http://localhost:8501');
  await page.getByText('VOC 품질진단', { exact: true }).click();
  await expect(page.getByText('Agent 관리', { exact: true })).toBeVisible();
  await page.getByText('Agent 관리', { exact: true }).click();
  await expect(page.getByRole('button', { name: 'Gemini 인증 점검' })).toBeVisible();
  await expect(page.getByText('Interpreter', { exact: true }).first()).toBeVisible({
    timeout: 30000,
  });
  await page.waitForTimeout(1500);
  await page.screenshot({
    path: '.artifacts/demo/02-agent-management.png',
    fullPage: true,
  });
});
