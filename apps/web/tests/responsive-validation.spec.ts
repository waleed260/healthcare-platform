import { test, expect } from "./fixtures";

const permissions = ["appointment.read", "patient.read", "billing.read", "website.read", "queue.read", "lead.read", "clinical.read", "report.read", "notification.read"];

async function installApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];

    if (path.endsWith("/auth/me")) {
      data = { user_id: "u1", clinic_id: "c1", display_name: "Staff", permissions };
    } else if (path.endsWith("/notifications")) {
      data = [];
    } else if (path.endsWith("/branches")) {
      data = [{ id: "b1", name: "Main" }];
    } else if (path.endsWith("/doctors")) {
      data = [{ id: "d1", public_name: "Dr. Test" }];
    } else if (path.endsWith("/services")) {
      data = [{ id: "s1", name: "Consultation" }];
    }

    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
  });
}

const viewports = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1280, height: 800 },
] as const;

const pages = ["/dashboard", "/schedule", "/patients", "/queue"] as const;

test.describe("responsive validation", () => {
  for (const vp of viewports) {
    test(`${vp.name} (${vp.width}px): key pages render without horizontal scroll`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await installApi(page);

      for (const path of pages) {
        await page.goto(path);
        await page.waitForTimeout(500);
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
        expect(scrollWidth, `${path} at ${vp.width}px has horizontal scroll`).toBeLessThanOrEqual(clientWidth + 2);
      }
    });
  }

  test("mobile nav toggle is visible at 375px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await installApi(page);
    await page.goto("/dashboard");
    await expect(page.locator(".mobile-nav-toggle")).toBeVisible();
  });

  test("sidebar is visible at 1280px", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await installApi(page);
    await page.goto("/dashboard");
    await expect(page.locator(".workspace-sidebar")).toBeVisible();
  });
});
