import { test, expect } from "@playwright/test";

test.describe("AppShell layout", () => {
  test("main content area should be visible and usable", async ({ page }) => {
    await page.goto("/dashboard");
    const main = page.locator("#main-content");
    await expect(main).toBeVisible();

    const box = await main.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(300);
    expect(box?.height ?? 0).toBeGreaterThan(200);
  });

  test("rail navigation should be visible on desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/dashboard");
    const rail = page.locator(".rail").first();
    await expect(rail).toBeVisible();
  });

  test("no horizontal scroll on main content", async ({ page }) => {
    await page.goto("/dashboard");
    const scrollWidth = await page.locator("#main-content").evaluate(
      (el) => el.scrollWidth
    );
    const clientWidth = await page.locator("#main-content").evaluate(
      (el) => el.clientWidth
    );
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2); // 2px tolerance
  });
});

test.describe("Responsive breakpoints", () => {
  const viewports = [
    { name: "desktop", width: 1440, height: 900 },
    { name: "laptop", width: 1280, height: 800 },
    { name: "tablet", width: 768, height: 1024 },
    { name: "mobile", width: 390, height: 844 },
  ];

  for (const vp of viewports) {
    test(`dashboard at ${vp.name} (${vp.width}x${vp.height})`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/dashboard");
      await expect(page.locator("#main-content")).toBeVisible();
    });
  }
});
