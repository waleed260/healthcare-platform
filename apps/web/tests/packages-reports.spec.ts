import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const ME = {
  user_id: "00000000-0000-0000-0000-0000000000aa",
  clinic_id: "00000000-0000-0000-0000-000000000001",
  clinic_slug: "synthetic",
  display_name: "Synthetic Staff",
  email: "staff@synthetic.test",
  is_platform_admin: false,
  permissions: ["package.read", "package.manage", "report.read", "report.manage", "appointment.read", "patient.read", "notification.read", "queue.read", "lead.read", "billing.read", "website.read"],
};

const OVERVIEW = { active_definitions: 2, inactive_definitions: 1, total_sold: 5, active_patient_packages: 3, sessions_purchased: 20, sessions_used: 8, sessions_remaining: 12, expiring_30d: 1 };
const PACKAGES = [{ id: "p1", name: "Starter", description: "intro", total_price_minor: 8000, original_value_minor: 10000, currency: "USD", validity_days: 30, status: "active", version: 1, total_sessions: 3 }];
const SOURCES = [{ key: "package_sales", label: "Package Sales & Utilization", permission: "package.read", metrics: [{ key: "count", label: "Packages sold" }, { key: "sessions_used", label: "Sessions used" }], dimensions: [{ key: "day", label: "Day" }], filters: [{ key: "status", type: "text" }] }];

const REPORTING_SUMMARY = {
  period_days: 30, appointments: [], patients_created: 0, leads: [],
  kpis: { appointments: { current: 0, prior: 0 }, appointments_completed: { current: 0, prior: 0 }, no_shows: { current: 0, prior: 0 }, new_patients: { current: 0, prior: 0 }, leads: { current: 0, prior: 0 }, conversions: { current: 0, prior: 0 } },
  financial: null,
  queue: { arrivals: 0, completed: 0, cancelled: 0, waiting_now: 0, in_service_now: 0, backlog: 0, avg_wait_seconds: 0, wait_samples: 0 },
  package_utilization: { packages: 0, sessions_purchased: 0, sessions_used: 0, sessions_remaining: 0 },
  operational: { waiting_patients: 0, followups_due: 0, no_shows: 0, low_inventory: 0, followups: { overdue: 0, due_today: 0, upcoming: 0, completed: 0 }, inventory: { tracked: 0, in_stock: 0, low_stock: 0, out_of_stock: 0 } },
};

async function installApi(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const send = (data: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data }) });
    if (path.endsWith("/auth/me")) return send(ME);
    if (path.endsWith("/packages/overview")) return send(OVERVIEW);
    if (path.endsWith("/packages")) return send(PACKAGES);
    if (path.endsWith("/reports/sources")) return send(SOURCES);
    if (path.endsWith("/reports/run")) return send({ columns: [{ key: "count", label: "Packages sold", kind: "metric" }], rows: [{ count: 7 }] });
    if (path.endsWith("/reports")) return send([]);
    if (path.includes("/reporting-summary")) return send(REPORTING_SUMMARY);
    return send([]);
  });
}

test("packages page shows overview KPIs and the catalog", async ({ page }) => {
  await installApi(page);
  await page.goto("/packages");
  await expect(page.getByText("ACTIVE PACKAGES", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Starter" })).toBeVisible();
  await expect(page.getByRole("button", { name: /New package/ })).toBeVisible();
});

test("report builder previews an allow-listed report", async ({ page }) => {
  await installApi(page);
  await page.goto("/reports");
  await page.getByRole("tab", { name: "Report Builder" }).click();
  await expect(page.getByRole("heading", { name: "Report builder" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Packages sold" }).check();
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.locator(".report-table td").filter({ hasText: "7" })).toBeVisible();
});
