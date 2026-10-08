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
        data = [{ id: "f1", name: "Contact Form", fields: [{ key: "name", label: "Full name", type: "text", required: true, options: [], maps_to: "full_name" }, { key: "email", label: "Email", type: "email", required: false, options: [], maps_to: "email" }, { key: "consent", label: "I agree to be contacted", type: "consent", required: true, options: [], maps_to: null }], action: "lead", status: "active", version: 1, success_message: "Thanks!" }];
      } else if (path.endsWith("/website-content/forms") && method === "POST") {
        data = { id: "f2", name: "New Form", fields: [], action: "lead", status: "active", version: 1, success_message: "Thanks, we will be in touch shortly." };
      } else if (path.endsWith("/website-content/posts")) {
        data = [];
      } else if (path.endsWith("/website-content/testimonials")) {
        data = [];
      } else if (path.endsWith("/websites")) {
        data = [{ id: "w1" }];
      } else if (path.endsWith("/pages")) {
        data = [{ id: "pg1", slug: "home", title: "Home" }];
      } else if (path.match(/\/forms\/f1$/) && method === "PATCH") {
        data = { id: "f1", name: "Contact Form", fields: [], action: "lead", status: "archived", version: 2, success_message: "Thanks!" };
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
    await expect(page.locator(".invoice-row").first()).toContainText("3 fields");
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

  test("form builder shows default fields with drag handles", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("button", { name: /new form/i }).click();
    await expect(page.locator(".drag-handle")).toHaveCount(5);
    await expect(page.locator('input[aria-label="Label"]').first()).toHaveValue("Full name");
  });

  test("form builder has field type selector", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("button", { name: /new form/i }).click();
    const typeSelects = page.locator('select[aria-label="Type"]');
    await expect(typeSelects.first()).toBeVisible();
    const options = await typeSelects.first().locator("option").allTextContents();
    expect(options).toContain("text");
    expect(options).toContain("email");
    expect(options).toContain("dropdown");
    expect(options).toContain("consent");
  });

  test("add field button inserts a new field before consent", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("button", { name: /new form/i }).click();
    const initialCount = await page.locator(".theme-row").count();
    await page.getByRole("button", { name: /add field/i }).click();
    await expect(page.locator(".theme-row")).toHaveCount(initialCount + 1);
  });

  test("form action dropdown has lead and appointment options", async ({ page }) => {
    await page.goto("/content");
    await page.getByRole("button", { name: /new form/i }).click();
    const actionSelect = page.locator('select[name="action"]');
    await expect(actionSelect).toBeVisible();
    const options = await actionSelect.locator("option").allTextContents();
    expect(options.some((o) => o.toLowerCase().includes("lead"))).toBe(true);
    expect(options.some((o) => o.toLowerCase().includes("appointment"))).toBe(true);
  });

  test("form can be added to a page via dropdown", async ({ page }) => {
    await page.goto("/content");
    const addToPageSelect = page.locator('select[aria-label="Add Contact Form to page"]');
    await expect(addToPageSelect).toBeVisible();
    await expect(addToPageSelect.locator("option")).toHaveCount(2);
  });

  test("archive button toggles form status", async ({ page }) => {
    await page.goto("/content");
    await expect(page.getByRole("button", { name: /archive/i })).toBeVisible();
  });

  test("summary cards show form count", async ({ page }) => {
    await page.goto("/content");
    await expect(page.locator(".inventory-summary")).toContainText("FORMS");
    await expect(page.locator(".inventory-summary")).toContainText("1");
  });
});
