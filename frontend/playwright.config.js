// playwright.config.js
module.exports = {
  testDir: './tests',
  timeout: 30000,
  expect: {
    timeout: 5000
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
    projects: [
      {
        name: 'chromium',
        use: {
          browserName: 'chromium',
          viewport: { width: 360, height: 800 },
          ignoreHTTPSErrors: true,
          headless: false, // true voor CI/CD
          baseURL: 'http://localhost:3000',
        },
      },
    ],
};
