import { test, expect } from "@playwright/test";

const routes = [
  "/",
  "/dashboard",
  "/projects",
  "/models",
  "/worker",
  "/tasks",
  "/prompts",
  "/study/library",
  "/memory",
  "/graphs",
  "/reader-agents",
  "/audit",
];

test.describe("UI smoke — routes should not crash", () => {
  for (const route of routes) {
    test(`route ${route} should render without white screen`, async ({ page }) => {
      await page.goto(route);
      await expect(page.locator("#root")).toBeVisible();
      // Main content area should exist
      await expect(page.locator("#main-content")).toBeVisible();
    });
  }
});
