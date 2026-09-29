import { test, expect } from "./fixtures";

test.describe("tenant isolation verification panel", () => {
  async function install(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];
      if (path.endsWith("/auth/me")) data = { user_id: "platform-admin", clinic_id: null, is_platform_admin: true, permissions: ["admin.support.access", "audit.read"] };
      if (path.endsWith("/admin/clinics")) data = [
        { id: "clinic-a", name: "Clinic A", slug: "clinic-a", status: "active", timezone: "UTC", locale: "en-US" },
        { id: "clinic-b", name: "Clinic B", slug: "clinic-b", status: "active", timezone: "UTC", locale: "en-US" },
      ];
      if (path.endsWith("/admin/tenant-isolation")) data = { required_permissions: ["admin.support.access", "audit.read"], tables: [
        { table_name: "patients", label: "Patients", rls_enabled: true, rls_forced: true, has_policy: true },
        { table_name: "appointments", label: "Appointments", rls_enabled: true, rls_forced: true, has_policy: true },
      ], recent_attempts: [] };
      if (path.endsWith("/admin/tenant-isolation/check")) {
        const broken = process.env.BREAK_TENANT_ISOLATION === "1";
        data = { overall: broken ? "violation" : "isolated", tables: [
          { table_name: "patients", label: "Patients", status: broken ? "violation" : "isolated", visible_rows: broken ? 1 : 0 },
          { table_name: "appointments", label: "Appointments", status: broken ? "violation" : "isolated", visible_rows: broken ? 1 : 0 },
        ] };
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data }) });
    });
  }

  test("reports isolated for two seeded clinics", async ({ page }) => {
    test.skip(process.env.BREAK_TENANT_ISOLATION === "1", "Healthy control is run without the fault switch.");
    await install(page);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Tenant isolation verification" })).toBeVisible();
    await expect(page.getByLabel("Clinic A").locator('option[value="clinic-a"]')).toHaveCount(1);
    await page.getByLabel("Clinic A").selectOption("clinic-a");
    await page.getByLabel("Clinic B").selectOption("clinic-b");
    await page.getByRole("button", { name: /run isolation check/i }).click();
    await expect(page.getByText("Isolated", { exact: true })).toBeVisible();
    await expect(page.getByText("Clinic A cannot see Clinic B", { exact: true })).toBeVisible();
    await expect(page.getByText("Synthetic Patient")).not.toBeVisible();
  });

  test("reports a deliberately broken isolation check", async ({ page }) => {
    test.skip(process.env.BREAK_TENANT_ISOLATION !== "1", "Negative control is run with BREAK_TENANT_ISOLATION=1.");
    await install(page);
    await page.goto("/admin");
    await page.getByLabel("Clinic A").selectOption("clinic-a");
    await page.getByLabel("Clinic B").selectOption("clinic-b");
    await page.getByRole("button", { name: /run isolation check/i }).click();
    await expect(page.getByText("Violation detected", { exact: true })).toBeVisible();
    await expect(page.getByText("Cross-tenant rows were visible", { exact: true })).toBeVisible();
  });
});
