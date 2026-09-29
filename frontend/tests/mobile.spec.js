// tests/mobile.spec.js
const { test, expect } = require('@playwright/test');

test('mobile responsive acceptance at 360x800', async ({ page }) => {
  // Netwerkisolatie: alleen localhost/127.0.0.1 wordt toegestaan
  await page.route('**/*', (route) => {
    const { hostname } = new URL(route.request().url());
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return route.continue();
    }
    return route.abort();
  });

  // Viewport 360x800 wordt ingesteld VÓÓR navigatie
  await page.setViewportSize({ width: 360, height: 800 });

  // Navigatie naar lokale frontend (baseURL http://localhost:3000)
  await page.goto('/');

  // Stabiele UI readiness: auto-retry assertions in plaats van vaste slaaptijd
  await expect(page.getByText('Nieuws Piet').first()).toBeVisible();
  await expect(page.locator('nav')).toBeVisible();
  await expect(page.locator('main')).toBeVisible();
  await expect(page.getByText('Nog geen nieuws beschikbaar')).toBeVisible();

  // Geen horizontale scrolling
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});
