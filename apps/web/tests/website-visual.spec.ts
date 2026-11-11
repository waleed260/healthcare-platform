import { test } from "./fixtures";
import type { Page } from "@playwright/test";

async function installWebsiteApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let data: unknown = [];
    if (path.endsWith("/auth/me")) {
      data = { user_id: "u1", clinic_id: "c1", clinic_slug: "synthetic-clinic", permissions: ["website.read", "website.edit", "website.publish"] };
    } else if (path.endsWith("/auth/csrf")) {
      data = { token: "synthetic-csrf" };
    } else if (path.endsWith("/websites") && route.request().method() === "GET") {
      data = [{ id: "w1", name: "Synthetic Clinic Website", template_key: "calm_clinic", status: "draft", version: 2, brand: {}, draft_version_id: "v1", live_version_id: null }];
    } else if (path.endsWith("/websites/w1")) {
      data = { id: "w1", name: "Synthetic Clinic Website", template_key: "calm_clinic", status: "draft", version: 2, brand: { palette: { primary: "#274c42", surface: "#f8f6f1" } }, draft_version_id: "v1", live_version_id: null };
    } else if (path.endsWith("/websites/w1/pages")) {
      data = [{ id: "p1", slug: "/", title: "Home", version: 1, seo_title: null, seo_description: null }, { id: "p2", slug: "/about", title: "About", version: 1, seo_title: null, seo_description: null }];
    } else if (path.endsWith("/websites/w1/pages/p1/sections")) {
      data = [
        { id: "s1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Care that feels considered.", body: "Welcome to our clinic.", button_label: "Book", button_href: "#appointment" }, is_visible: true, version: 1 },
        { id: "s2", section_type: "services", layout_key: "cards", position: 1, content: { heading: "Our services", body: "What we offer.", items: [{ title: "Consult", description: "Thorough assessment." }] }, is_visible: true, version: 1 },
      ];
    } else if (path.endsWith("/websites/w1/versions")) {
      data = [{ id: "v1", version_number: 1, published_at: null, created_at: "2026-11-01T08:00:00Z" }];
    } else if (path.endsWith("/websites/w1/themes")) {
      data = [];
    } else if (path.endsWith("/websites/w1/validation")) {
      data = { valid: true, code: null, message: null };
    } else if (path.endsWith("/websites/domains")) {
      data = [];
    } else if (path.endsWith("/websites/media") && route.request().method() === "GET") {
      data = [];
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "synthetic" } }) });
  });
}

test.describe("Website page visual QA", () => {
  test("renders main editor", async ({ page }) => {
    await installWebsiteApi(page);
    await page.goto(`/website`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/website-editor.png", fullPage: true });
  });

  test("renders empty-state when no sites", async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];
      if (path.endsWith("/auth/me")) data = { user_id: "u1", clinic_id: "c1", clinic_slug: "synthetic-clinic", permissions: ["website.read", "website.edit"] };
      else if (path.endsWith("/auth/csrf")) data = { token: "csrf" };
      else if (path.endsWith("/websites") && route.request().method() === "GET") data = [];
      else if (path.endsWith("/websites/domains")) data = [];
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "x" } }) });
    });
    await page.goto(`/website`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/website-empty.png", fullPage: true });
  });

  test("renders mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installWebsiteApi(page);
    await page.goto(`/website`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/website-mobile.png", fullPage: true });
  });
});
