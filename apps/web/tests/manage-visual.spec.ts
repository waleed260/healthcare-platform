import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

async function installManageApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let data: unknown = [];
    if (path.endsWith("/auth/me")) {
      data = {
        user_id: "user-1",
        clinic_id: "clinic-1",
        is_platform_admin: false,
        permissions: [
          "service.read", "service.manage",
          "staff.read", "staff.manage",
          "clinic.read", "clinic.update",
          "specialty.read",
          "branch.read",
          "admin.plan.manage",
        ],
      };
    } else if (path.endsWith("/auth/csrf")) {
      data = { token: "synthetic-csrf" };
    } else if (path.endsWith("/services")) {
      data = [
        { id: "svc-1", name: "HydraFacial", category: "Skin", short_description: "Hydration and exfoliation.", full_description: null, duration_minutes: 60, buffer_before_minutes: 5, buffer_after_minutes: 10, price_mode: "exact", amount_minor: 15000, currency: "USD", approval_mode: "instant", visibility: "public", status: "active", version: 1 },
        { id: "svc-2", name: "Teeth Cleaning", category: "Dental", short_description: null, full_description: null, duration_minutes: 45, buffer_before_minutes: 0, buffer_after_minutes: 0, price_mode: "exact", amount_minor: 8000, currency: "USD", approval_mode: "staff_approval", visibility: "public", status: "active", version: 1 },
        { id: "svc-3", name: "Laser Hair Removal", category: "Laser", short_description: "Permanent reduction.", full_description: null, duration_minutes: 30, buffer_before_minutes: 0, buffer_after_minutes: 0, price_mode: "starting_at", amount_minor: 12000, currency: "USD", approval_mode: "instant", visibility: "hidden", status: "archived", version: 2 },
      ];
    } else if (path.endsWith("/branches")) {
      data = [
        { id: "br-1", code: "MAIN", name: "Main Clinic", timezone: "UTC", phone: null, status: "active", version: 1 },
        { id: "br-2", code: "DT", name: "Downtown", timezone: "UTC", phone: null, status: "active", version: 1 },
      ];
    } else if (path.endsWith("/staff/users")) {
      data = [
        { id: "user-1", display_name: "Admin User", normalized_email: "admin@clinic.test", status: "active", last_login_at: "2026-11-10T09:00:00Z", version: 1 },
        { id: "user-2", display_name: "Dr Sarah Chen", normalized_email: "sarah@clinic.test", status: "active", last_login_at: null, version: 1 },
        { id: "user-3", display_name: "Reception", normalized_email: "front@clinic.test", status: "suspended", last_login_at: "2026-10-01T12:00:00Z", version: 2 },
      ];
    } else if (path.endsWith("/staff/roles")) {
      data = [
        { id: "role-1", name: "clinic_admin", is_system: true, permissions: [{ code: "clinic.read" }, { code: "clinic.update" }, { code: "staff.read" }, { code: "staff.manage" }] },
        { id: "role-2", name: "doctor", is_system: true, permissions: [{ code: "patient.read" }, { code: "encounter.manage" }] },
        { id: "role-3", name: "lab_tech", is_system: false, permissions: [{ code: "lab.read" }] },
      ];
    } else if (path.endsWith("/specialties/library")) {
      data = [
        { id: "sp-1", code: "DERM", name: "Dermatology", description: "Skin and hair concerns.", enabled: true },
        { id: "sp-2", code: "DENT", name: "Dentistry", description: "Oral and dental care.", enabled: false },
        { id: "sp-3", code: "CARD", name: "Cardiology", description: "Heart and vascular.", enabled: false },
      ];
    } else if (path.endsWith("/upgrade-requests") && !path.includes("/cancel")) {
      data = [
        { id: "ur-1", kind: "specialty", target_code: "DENT", message: "Dentistry needed.", status: "pending", decision_note: null, created_at: "2026-11-01T08:00:00Z" },
      ];
    } else if (path.endsWith("/catalog/service-templates")) {
      data = [
        { id: "tpl-1", name: "Standard Consultation", category: "General", specialty_code: null, duration_minutes: 30, amount_minor: 5000, currency: "USD" },
        { id: "tpl-2", name: "Dental Cleaning", category: "Dental", specialty_code: "DENT", duration_minutes: 45, amount_minor: 10000, currency: "USD" },
      ];
    } else if (path.endsWith("/staff/invitations")) {
      data = [
        { id: "inv-1", email: "new.doctor@clinic.test", status: "pending", created_at: "2026-11-10T14:00:00Z" },
      ];
    } else if (path.endsWith("/governance/feature-limits")) {
      data = [
        { feature: "branches", current_usage: 2, limit_value: 5 },
        { feature: "staff_members", current_usage: 3, limit_value: 10 },
        { feature: "services", current_usage: 3, limit_value: 50 },
        { feature: "patients_total", current_usage: 950, limit_value: 1000 },
      ];
    } else if (path.endsWith("/governance/subscription")) {
      data = { id: "sub-1", code: "pro", name: "Pro Plan", status: "active", starts_at: "2026-01-01T00:00:00Z", ends_at: "2027-01-01T00:00:00Z" };
    } else if (path.endsWith("/staff/permissions")) {
      data = [
        { code: "clinic.read", description: "Read clinic details" },
        { code: "clinic.update", description: "Update clinic settings" },
        { code: "staff.read", description: "View staff list" },
        { code: "staff.manage", description: "Invite and manage staff" },
        { code: "service.read", description: "View services" },
        { code: "service.manage", description: "Create and edit services" },
        { code: "patient.read", description: "View patient records" },
        { code: "patient.manage", description: "Edit patient records" },
        { code: "encounter.manage", description: "Manage encounters" },
        { code: "billing.read", description: "View invoices" },
        { code: "billing.manage", description: "Create and edit invoices" },
      ];
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "synthetic" } }) });
  });
}

test.describe("Manage page visual QA", () => {
  for (const tab of ["services", "staff", "roles", "modules"] as const) {
    test(`renders ${tab} tab`, async ({ page }) => {
      await installManageApi(page);
      await page.goto(`/manage?tab=${tab}`);
      await page.waitForLoadState("networkidle");
      await expect(page.locator(".manage-page")).toBeVisible();
      await page.screenshot({ path: `test-results/manage-${tab}.png`, fullPage: true });
    });
  }

  test("renders services tab on mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installManageApi(page);
    await page.goto("/manage?tab=services");
    await page.waitForLoadState("networkidle");
    await expect(page.locator(".manage-page")).toBeVisible();
    await page.screenshot({ path: "test-results/manage-mobile.png", fullPage: true });
  });

  test("role editor drawer renders with sticky group header", async ({ page }) => {
    await installManageApi(page);
    await page.goto("/manage?tab=roles");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: /Create role/ }).click();
    await expect(page.locator(".role-permissions")).toBeVisible();
    await page.screenshot({ path: "test-results/manage-role-editor.png", fullPage: true });
  });
});
