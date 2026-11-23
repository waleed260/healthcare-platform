import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { resolve } from "node:path";

// expires_at in the past so the support session renders as EXPIRED immediately
// (the console computes status at render time; there is no live tick timer).
const EXPIRED_AT = "2000-01-01T00:00:00Z";

async function installAdminApi(page: Page, platformAdmin: boolean, supportExpiresAt = EXPIRED_AT) {
  let clinicStatus = "active";
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    let data: unknown = [];
    if (path.endsWith("/auth/me")) data = { user_id: "synthetic-user", clinic_id: platformAdmin ? null : "clinic-1", is_platform_admin: platformAdmin, permissions: platformAdmin ? [] : ["patient.read"] };
    if (path.endsWith("/admin/clinics/clinic-1/lifecycle") && method === "POST") { clinicStatus = "suspended"; data = { id: "clinic-1", name: "Synthetic Care", slug: "synthetic-care", status: clinicStatus, timezone: "UTC", locale: "en-US", version: 2, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-09-28T08:00:00Z", subscription_status: null, renewal_at: null, subscription_ends_at: null, plan_name: null, plan_code: null }; }
    if (path.endsWith("/admin/clinics")) data = [{ id: "clinic-1", name: "Synthetic Care", slug: "synthetic-care", status: clinicStatus, timezone: "UTC", locale: "en-US", version: 1, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-09-28T08:00:00Z", subscription_status: null, renewal_at: null, subscription_ends_at: null, plan_name: null, plan_code: null }];
    if (path.includes("/admin/clinics/clinic-1/overview")) data = { clinic: { id: "clinic-1", name: "Synthetic Care", status: clinicStatus }, accounts: { active_users: 3, total_users: 5, last_login_at: "2026-09-28T08:00:00Z" }, activity: { appointments_total: 12, appointments_30d: 4, patients_total: 4 }, modules: ["dentistry"] };
    if (path.endsWith("/admin/metrics")) data = { database_pool: { size: 10, checked_out: 2, overflow: 0 }, billing: { active: 1, trialing: 0, past_due: 0, cancelled: 0 }, background_jobs: { queued: 1, running: 0, failed: 0 }, telemetry: { appointments: { requested: 4, confirmed: 3, completed: 2, cancelled: 0 }, scan_backlog: 0, storage_failures: 0, publish_failures: 0 } };
    if (path.endsWith("/admin/support-access") && method === "GET") data = [{ id: "support-1", clinic_id: "clinic-1", requested_by_user_id: "requester-1", approved_by_user_id: "approver-1", reason: "Synthetic support review", permissions: ["patient.read"], starts_at: "2026-09-28T08:00:00Z", expires_at: supportExpiresAt, revoked_at: null }];
    if (path.endsWith("/admin/audit")) data = [];
    if (path.endsWith("/admin/plans")) data = [{ id: "plan-1", code: "starter", name: "Starter", active: true, created_at: "2026-01-01T00:00:00Z", limits: {} }];
    if (path.endsWith("/admin/announcements")) data = [{ id: "announcement-1", title: "Synthetic maintenance window", body: "A synthetic platform notice.", severity: "info", starts_at: "2026-09-28T08:00:00Z", ends_at: null, created_at: "2026-09-28T08:00:00Z" }];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "synthetic-request" } }) });
  });
}

test.describe("platform admin access", () => {
  test("platform admin sees the developer console without clinical content", async ({ page }) => {
    const clinicalRequests: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (/\/api\/v1\/(patients|appointments|operations|queue)(\/|$)/.test(path)) clinicalRequests.push(path);
    });
    await installAdminApi(page, true);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Developer Console" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Registered clinics" })).toBeVisible();
    await expect(page.getByText("Synthetic Care", { exact: true })).toBeVisible({ timeout: 15000 });
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
    await page.getByText("Synthetic Care", { exact: true }).click();
    await page.getByRole("button", { name: "Suspend clinic" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Suspend", exact: true }).click();
    await expect(page.getByText("SUSPENDED", { exact: true })).toBeVisible({ timeout: 15000 });
  });

  test("platform admin sees an expired support session without a revoke action", async ({ page }) => {
    await installAdminApi(page, true);
    await page.goto("/admin");
    await page.getByRole("tab", { name: "Support" }).click();
    await expect(page.getByText("Synthetic support review", { exact: true })).toBeVisible();
    await expect(page.getByText("EXPIRED", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Revoke" })).not.toBeVisible();
  });

  test("clinic staff receive an access-restricted page", async ({ page }) => {
    await installAdminApi(page, false);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: /access restricted/i })).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("heading", { name: "Developer Console" })).not.toBeVisible();
  });

  test("a failed panel request degrades gracefully", async ({ page }) => {
    await installAdminApi(page, true);
    // A failing clinic directory must not take down the console (panels tolerate partial failure).
    await page.route("**/api/v1/admin/clinics**", (r) => r.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { message: "Synthetic clinic directory outage." } }) }));
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Developer Console" })).toBeVisible();
    await expect(page.getByText(/no clinics registered/i)).toBeVisible();
  });
});
