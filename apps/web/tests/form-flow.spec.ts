import { test, expect } from "./fixtures";

const permissions = ["website.read", "website.edit", "website.publish"];

test.describe("form flow: create form → verify fields", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      let data: unknown = [];

      if (path.endsWith("/auth/me")) {
        data = { user_id: "u1", clinic_id: "c1", display_name: "Staff", permissions };
      } else if (path.endsWith("/notifications")) {
        data = [];
      } else if (path.endsWith("/website-content/forms") && method === "GET") {
        data = [{ id: "f1", name: "Contact Form", fields: [{ key: "name", label: "Full name", type: "text", required: true, options: [], maps_to: "full_name" }, { key: "email", label: "Email", type: "email", required: false, options: [], maps_to: "email" }], action: "lead", status: "active", version: 1, success_message: "Thanks!" }];
      } else if (path.endsWith("/website-content/forms") && method === "POST") {
        data = { id: "f2", name: "New Form", fields: [], action: "lead", status: "active", version: 1 };
      } else if (path.endsWith("/website-content/posts")) {
        data = [];
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

  test("form list shows existing forms", async ({ page }) => {
    await page.goto("/content");
    await expect(page.locator(".invoice-row")).toHaveCount(1);
    await expect(page.locator(".invoice-row").first()).toContainText("Contact Form");
  });

  test("form shows field count", async ({ page }) => {
    await page.goto("/content");
    await expect(page.locator(".invoice-row").first()).toContainText("2 fields");
  });

  test("new form button is visible", async ({ page }) => {
    await page.goto("/content");
    await expect(page.getByRole("button", { name: /new form/i })).toBeVisible();
  });

  test("clicking new form toggles the form builder", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("button", { name: /new form/i }).click();
    await expect(page.locator(".manage-form")).toBeVisible();
    await expect(page.locator('input[name="name"]')).toBeVisible();
  });
});
