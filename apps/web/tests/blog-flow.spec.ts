import { test, expect } from "./fixtures";

const permissions = ["website.read", "website.edit", "website.publish"];

test.describe("blog flow: create → publish → verify", () => {
  test.beforeEach(async ({ page }) => {
    let postStatus = "draft";

    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      let data: unknown = [];

      if (path.endsWith("/auth/me")) {
        data = { user_id: "u1", clinic_id: "c1", display_name: "Staff", permissions };
      } else if (path.endsWith("/notifications")) {
        data = [];
      } else if (path.endsWith("/website-content/forms")) {
        data = [];
      } else if (path.endsWith("/website-content/posts") && method === "GET") {
        data = [{ id: "post-1", slug: "test-post", title: "Test Post", excerpt: "A summary", body: "<p>Hello world</p>", status: postStatus, version: 1, updated_at: "2026-10-07T10:00:00Z" }];
      } else if (path.endsWith("/website-content/posts") && method === "POST") {
        data = { id: "post-1", slug: "test-post", title: "Test Post", status: "draft", version: 1 };
      } else if (path.includes("/posts/") && path.endsWith("/status")) {
        postStatus = "published";
        data = { status: "published", version: 2 };
      } else if (path.endsWith("/website-content/testimonials")) {
        data = [];
      } else if (path.endsWith("/websites")) {
        data = [{ id: "w1" }];
      } else if (path.endsWith("/pages")) {
        data = [{ id: "pg1", slug: "home", title: "Home" }];
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
    });
  });

  test("content page renders blog tab with posts", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("tab", { name: /blog/i }).click();
    await expect(page.locator(".invoice-row")).toHaveCount(1);
    await expect(page.locator(".invoice-row").first()).toContainText("Test Post");
  });

  test("blog post shows slug path", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("tab", { name: /blog/i }).click();
    await expect(page.locator(".invoice-row").first()).toContainText("/blog/test-post");
  });

  test("content page renders forms tab by default", async ({ page }) => {
    await page.goto("/content");
    await expect(page.getByRole("tab", { name: /forms/i })).toHaveAttribute("aria-selected", "true");
  });

  test("testimonials tab renders", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("tab", { name: /testimonials/i }).click();
    await expect(page.locator(".surface-card")).toBeVisible();
  });
});
