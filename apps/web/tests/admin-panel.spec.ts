import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { resolve } from "node:path";

async function installAdminApi(page: Page, platformAdmin: boolean, failClinicsOnce = false, supportExpiresAt = "2099-09-28T08:30:00Z") {
  let failedClinics = false;
  let clinicStatus = "active";
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (failClinicsOnce && path.endsWith("/admin/clinics") && !failedClinics) {
      failedClinics = true;
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { message: "Synthetic clinic directory outage." } }) });
      return;
    }
    let data: unknown = [];
    if (path.endsWith("/auth/me")) data = { user_id: "synthetic-user", clinic_id: platformAdmin ? null : "clinic-1", is_platform_admin: platformAdmin, permissions: platformAdmin ? [] : ["patient.read"] };
    if (path.endsWith("/admin/clinics/clinic-1/lifecycle") && route.request().method() === "POST") { clinicStatus = "suspended"; data = { id: "clinic-1", name: "Synthetic Care", slug: "synthetic-care", status: clinicStatus, timezone: "UTC", locale: "en-US", version: 2 }; }
    if (path.endsWith("/admin/clinics")) data = [{ id: "clinic-1", name: "Synthetic Care", slug: "synthetic-care", status: clinicStatus, timezone: "UTC", locale: "en-US", version: 1 }];
    if (path.endsWith("/admin/plans")) data = [{ id: "plan-1", code: "starter", name: "Starter", active: true, limits: {} }];
    if (path.endsWith("/admin/announcements")) data = [{ id: "announcement-1", title: "Synthetic maintenance window", body: "A synthetic platform notice.", severity: "info", starts_at: "2026-09-28T08:00:00Z", ends_at: null }];
    if (path.endsWith("/admin/support-access") && route.request().method() === "GET") data = [{ id: "support-1", clinic_id: "clinic-1", requested_by_user_id: "requester-1", approved_by_user_id: "approver-1", reason: "Synthetic support review", permissions: ["patient.read"], starts_at: "2026-09-28T08:00:00Z", expires_at: supportExpiresAt, revoked_at: null }];
    if (path.endsWith("/admin/tenant-isolation")) data = { required_permissions: ["admin.support.access", "audit.read"], tables: [{ table_name: "patients", label: "Patients", rls_enabled: true, rls_forced: true, has_policy: true }], recent_attempts: [] };
    if (path.endsWith("/admin/metrics")) data = { background_jobs: { queued: 1, running: 0, failed: 0 }, telemetry: { appointments: { total: 4, completed: 2, cancelled: 0 }, scan_backlog: 0, publish_failures: 0 } };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "synthetic-request" } }) });
  });
}

test.describe("platform admin access", () => {
  test("platform admin sees aggregate panels without clinical content", async ({ page }) => {
    const clinicalRequests: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (/\/api\/v1\/(patients|appointments|operations|queue)(\/|$)/.test(path)) clinicalRequests.push(path);
    });
    await installAdminApi(page, true);
    await page.goto("/admin");
    await expect(page.getByText("Platform administration", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Clinics" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Announcements" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Governance surfaces" })).toBeVisible();
    await expect(page.getByRole("row", { name: /Synthetic Care synthetic-care/ }).getByRole("strong")).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Synthetic Patient")).not.toBeVisible();
    expect(clinicalRequests).toEqual([]);
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.screenshot({ path: resolve(process.cwd(), `../../docs/reports/screenshots/admin-panel-${width}.png`), fullPage: true });
    }
  });

  test("platform admin confirms and submits a clinic suspension", async ({ page }) => {
    await installAdminApi(page, true);
    await page.goto("/admin");
    await page.getByRole("button", { name: "Suspend" }).click({ force: true });
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("dialog").getByLabel("Reason").fill("Suspicious activity review");
    await page.getByRole("dialog").getByRole("button", { name: /confirm suspend/i }).click();
    await expect(page.getByText("suspended", { exact: true })).toBeVisible();
  });

  test("platform admin shows a support session expiring live", async ({ page }) => {
    await installAdminApi(page, true, false, new Date(Date.now() + 1200).toISOString());
    await page.goto("/admin");
    await expect(page.getByText("Synthetic support review", { exact: true })).toBeVisible();
    await expect(page.getByText("Expired", { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("button", { name: "Revoke" })).not.toBeVisible();
  });

  test("clinic staff receive an access-restricted page", async ({ page }) => {
    await installAdminApi(page, false);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: /not your workspace/i })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Platform administration", { exact: true })).not.toBeVisible();
  });

  test("platform admin can retry a failed panel request", async ({ page }) => {
    await installAdminApi(page, true, true);
    await page.goto("/admin");
    await expect(page.locator(".workspace-alert")).toContainText("Synthetic clinic directory outage.");
    await page.getByRole("button", { name: /try again/i }).click();
    await expect(page.getByRole("heading", { name: "Clinics" })).toBeVisible();
    await expect(page.getByRole("row", { name: /Synthetic Care synthetic-care/ }).getByRole("strong")).toBeVisible();
  });
});
