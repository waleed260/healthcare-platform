import { test, expect } from "./fixtures";

test.describe("preview token validation", () => {
  const validSnapshot = {
    template_key: "calm_clinic",
    brand: { colors: { primary: "#2563eb" } },
    pages: [{ slug: "home", title: "Home", sections: [{ id: "s1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Draft Preview", body: "This is a draft page" }, is_visible: true }] }],
  };

  test("valid preview token renders draft content", async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes("/public/sites/slug")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { snapshot: validSnapshot }, meta: { request_id: "r1" } }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [], meta: { request_id: "r1" } }) });
      }
    });
    await page.goto("/demo-clinic?preview=tok_valid_123");
    await expect(page.getByText("Draft Preview")).toBeVisible();
  });

  test("expired preview token shows rejection", async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes("/public/sites/slug")) {
        await route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ error: { message: "Preview token expired" }, meta: { request_id: "r1" } }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [], meta: { request_id: "r1" } }) });
      }
    });
    await page.goto("/demo-clinic?preview=tok_expired_456");
    await expect(page.getByText(/expired|error|unavailable/i)).toBeVisible();
  });

  test("no undefined URLs appear in page requests", async ({ page }) => {
    const requestUrls: string[] = [];
    await page.route("**/api/v1/**", async (route) => {
      requestUrls.push(route.request().url());
      const path = new URL(route.request().url()).pathname;
      if (path.includes("/public/sites/slug")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { snapshot: validSnapshot }, meta: { request_id: "r1" } }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [], meta: { request_id: "r1" } }) });
      }
    });
    await page.goto("/demo-clinic");
    await page.waitForTimeout(1000);
    const undefinedUrls = requestUrls.filter((url) => url.includes("undefined"));
    expect(undefinedUrls, "No requests should contain 'undefined' in the URL").toHaveLength(0);
  });
});
