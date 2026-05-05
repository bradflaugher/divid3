import { defineConfig, devices } from '@playwright/test';

/**
 * The semantic-routing tests load a ~22 MB ONNX model on first run.
 * Each Playwright test gets a fresh browser context (so a cold IndexedDB),
 * which means every test re-downloads from the local server. Two workers
 * keep wall-clock time reasonable without thrashing CI memory.
 *
 * We run four projects:
 *
 *   - `chromium`      desktop Chrome (the original suite)
 *   - `firefox`       desktop Firefox — Gecko has its own quirks around
 *                     visualViewport, IndexedDB, and ONNX/WASM that
 *                     Chromium and WebKit don't surface
 *   - `webkit`        desktop Safari engine — catches Safari-specific
 *                     bugs in the on-device ML pipeline
 *   - `mobile-safari` iPhone 13 viewport on the WebKit engine — catches
 *                     iOS layout regressions and the soft-keyboard /
 *                     visual-viewport behavior.
 *
 * Some tests are mobile-only or webkit-only; they `test.skip()` when
 * run on the wrong project so the suite stays valid across all four.
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  workers: process.env.CI ? 2 : undefined,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 90_000,
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 13'] },
    },
  ],
  webServer: {
    command: 'npx serve -l 3000 .',
    url: 'http://localhost:3000/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
