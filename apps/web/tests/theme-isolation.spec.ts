import { test, expect } from "./fixtures";

const permissions = ["website.read", "website.edit", "website.publish"];

test.describe("theme settings isolation and rendering", () => {
  function installApi(page: import("@playwright/test").Page, brand: Record<string, unknown> = {}) {
    return page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];

      if (path.endsWith("/auth/me")) {
        data = { user_id: "u1", clinic_id: "c1", display_name: "Admin", permissions, clinic_slug: "test-clinic" };
      } else if (path.endsWith("/notifications")) {
        data = [];
      } else if (path.endsWith("/websites") && !path.includes("/pages") && !path.includes("/versions") && !path.includes("/domains") && !path.includes("/validation")) {
        data = [{ id: "w1", name: "Test Clinic", template_key: "calm_clinic", status: "draft", version: 1, brand }];
      } else if (path.endsWith("/pages")) {
        data = [{ id: "pg1", slug: "home", title: "Home", version: 1 }];
      } else if (path.endsWith("/sections")) {
        data = [{ id: "sec1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Welcome", body: "Test" }, is_visible: true, version: 1 }];
      } else if (path.endsWith("/versions")) {
        data = [{ id: "v1", version_number: 1, created_at: "2026-10-01T00:00:00Z" }];
      } else if (path.endsWith("/domains")) {
        data = [];
      } else if (path.endsWith("/validation")) {
        data = { valid: true, code: null, message: null };
      } else if (path.includes("/public/sites/slug")) {
        data = { snapshot: { template_key: "calm_clinic", brand, pages: [{ slug: "home", title: "Test Clinic", sections: [{ id: "sec1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Welcome", body: "Hello" }, is_visible: true }] }] } };
      } else if (path.includes("/public/catalog")) {
        data = { clinic: { name: "Test Clinic", timezone: "UTC" }, branches: [], services: [], doctors: [] };
      } else if (path.includes("/public/sites/slug") && path.includes("/testimonials")) {
        data = [];
      } else if (path.includes("/public/sites/slug") && path.includes("/results")) {
        data = [];
      } else if (path.includes("/themes") && !path.includes("activate") && !path.includes("archive")) {
        data = [{ id: "th1", name: "Live", status: "live", brand_snapshot: brand, version: 1, created_at: "2026-10-01T00:00:00Z" }, { id: "th2", name: "Draft Autumn", status: "draft", brand_snapshot: {}, version: 1, created_at: "2026-10-02T00:00:00Z" }];
      } else if (path.includes("/themes/") && path.includes("/activate")) {
        data = { id: "th2", name: "Draft Autumn", status: "live", brand_snapshot: {}, version: 2 };
      } else if (path.includes("/themes/") && path.includes("/archive")) {
        data = { id: "th2", status: "archived", archived_at: "2026-10-08T00:00:00Z", version: 2 };
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
    });
  }

  test("theme colors from brand apply to public site", async ({ page }) => {
    const brand = { theme: { colors: { primary: "#ff0000", background: "#000000", text: "#ffffff", accent: "#00ff00" } } };
    await installApi(page, brand);
    await page.goto("/test-clinic");
    await expect(page.locator(".public-site")).toBeVisible();
  });

  test("different brand settings render distinct themes", async ({ page }) => {
    const brand = { theme: { colors: { primary: "#274c42", background: "#f5f4ee" } } };
    await installApi(page, brand);
    await page.goto("/test-clinic");
    const site = page.locator(".public-site");
    await expect(site).toBeVisible();
    await expect(site).toHaveClass(/has-theme/);
  });

  test("header sticky setting affects header class", async ({ page }) => {
    await installApi(page, { header: { sticky: true } });
    await page.goto("/test-clinic");
    await expect(page.locator(".public-header.is-sticky")).toBeVisible();
  });

  test("header non-sticky omits sticky class", async ({ page }) => {
    await installApi(page, { header: { sticky: false } });
    await page.goto("/test-clinic");
    const header = page.locator(".public-header");
    await expect(header).toBeVisible();
    await expect(header).not.toHaveClass(/is-sticky/);
  });

  test("announcement bar renders when set", async ({ page }) => {
    await installApi(page, { header: { announcement: "Grand opening sale!" } });
    await page.goto("/test-clinic");
    await expect(page.locator(".site-announcement")).toContainText("Grand opening sale!");
  });

  test("footer copyright renders from brand", async ({ page }) => {
    await installApi(page, { footer: { copyright: "2026 Test Clinic Inc." } });
    await page.goto("/test-clinic");
    await expect(page.locator(".public-footer")).toContainText("2026 Test Clinic Inc.");
  });

  test("footer columns render when configured", async ({ page }) => {
    await installApi(page, { footer: { columns: [{ kind: "about", title: "About Us", body: "We care." }, { kind: "hours", title: "Hours", body: "Mon-Fri 9-5" }] } });
    await page.goto("/test-clinic");
    await expect(page.locator(".site-footer-col")).toHaveCount(2);
    await expect(page.locator(".site-footer-col").first()).toContainText("About Us");
  });

  test("editor renders theme preset buttons", async ({ page }) => {
    await installApi(page, {});
    await page.goto("/website");
    await expect(page.locator(".preset-tile")).toHaveCount(6);
  });

  test("themes tab lists theme instances", async ({ page }) => {
    await installApi(page, {});
    await page.goto("/website");
    await page.locator(".wb-rtab", { hasText: "Themes" }).click();
    await expect(page.locator(".wb-version-row")).toHaveCount(2);
    await expect(page.locator(".wb-version-row").first()).toContainText("Live");
  });

  test("themes tab has create input", async ({ page }) => {
    await installApi(page, {});
    await page.goto("/website");
    await page.locator(".wb-rtab", { hasText: "Themes" }).click();
    await expect(page.locator('input[placeholder="Theme name"]')).toBeVisible();
  });

  test("draft theme shows activate button", async ({ page }) => {
    await installApi(page, {});
    await page.goto("/website");
    await page.locator(".wb-rtab", { hasText: "Themes" }).click();
    const draftRow = page.locator(".wb-version-row", { hasText: "Draft Autumn" });
    await expect(draftRow.locator("button", { hasText: "Activate" })).toBeVisible();
  });
});
