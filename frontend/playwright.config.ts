/**
 * Playwright config — Phase 0 脚手架 (不跑, Phase 9 启用).
 *
 * 三套 webServer 启动策略:
 * - e2e/smoke: 启动 dev server (vite + uvicorn 都需要)
 * - e2e/a11y: 同上, 跑 axe-core
 * - e2e/layout: 同上, 跑多视口截图回归
 *
 * 关键决策:
 * 1. baseURL 走 vite (5173), 不用 preview 端口 (避免 build 之后再跑)
 * 2. screenshot 模式: only-on-failure, Phase 9 视觉回归时改为 on
 * 3. reporter: list + html, html 写到 playwright-report/ (已 gitignore)
 * 4. workers: 1 (Phase 0 单测, Phase 9 可调高)
 *
 * Phase 9 时:
 *   pnpm exec playwright install chromium
 *   pnpm test:smoke
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'chromium-tablet',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 768 } },
    },
    {
      name: 'chromium-mobile',
      use: { ...devices['Pixel 5'] },
    },
  ],

  // Phase 0 不启 webServer (没有 e2e 测试). Phase 9 启用.
  // webServer: [
  //   { command: 'pnpm dev', port: 5173, reuseExistingServer: !process.env.CI, timeout: 60_000 },
  // ],
});