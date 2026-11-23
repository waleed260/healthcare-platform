import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const clinic = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Synthetic Care Clinic",
  slug: "synthetic-care",
  status: "active",
  timezone: "UTC",
  locale: "en-US",
  version: 1,
};

const dailyData = [
  { date: "2026-10-01", appointments: 8, new_patients: 2, revenue_minor: 120000, no_shows: 1 },
  { date: "2026-10-02", appointments: 12, new_patients: 3, revenue_minor: 180000, no_shows: 0 },
  { date: "2026-10-03", appointments: 5, new_patients: 1, revenue_minor: 75000, no_shows: 2 },
];

const channelData = [
  { channel: "google", leads: 40, converted: 12 },
  { channel: "referral", leads: 25, converted: 8 },
  { channel: "instagram", leads: 15, converted: 3 },
];

const funnelData = [
  { stage: "new", count: 80 },
  { stage: "contacted", count: 60 },
  { stage: "qualified", count: 40 },
  { stage: "appointment_booked", count: 25 },
  { stage: "visited", count: 18 },
  { stage: "converted", count: 12 },
];

const topServiceData = [
  { name: "Dental cleaning", count: 30, revenue_minor: 900000 },
  { name: "Consultation", count: 22, revenue_minor: 440000 },
  { name: "X-Ray", count: 15, revenue_minor: 375000 },
];

// /analytics redirects to /reports, whose summary KPIs load from
// /operations/reporting-summary. Without it `report` stays the default [] and the
// page throws on render, so the whole trends view must mock it too.
const reportSummary = {
  period_days: 30,
  appointments: [{ status: "completed", count: 15 }, { status: "cancelled", count: 10 }],
  patients_created: 7,
  leads: [{ status: "new", count: 12 }, { status: "converted", count: 8 }],
  kpis: {
    appointments: { current: 25, prior: 20 },
    appointments_completed: { current: 15, prior: 12 },
    no_shows: { current: 3, prior: 4 },
    new_patients: { current: 7, prior: 5 },
    leads: { current: 20, prior: 18 },
    conversions: { current: 8, prior: 6 },
  },
  financial: null,
  queue: { arrivals: 0, completed: 0, cancelled: 0, waiting_now: 0, in_service_now: 0, backlog: 0, avg_wait_seconds: 0, wait_samples: 0 },
  package_utilization: { packages: 0, sessions_purchased: 0, sessions_used: 0, sessions_remaining: 0 },
  operational: { waiting_patients: 0, followups_due: 0, no_shows: 0, low_inventory: 0, followups: { overdue: 0, due_today: 0, upcoming: 0, completed: 0 }, inventory: { tracked: 0, in_stock: 0, low_stock: 0, out_of_stock: 0 } },
};

async function installAnalyticsApi(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let data: unknown = [];

    if (path.endsWith("/auth/me")) {
      data = {
        user_id: "synthetic-user",
        clinic_id: clinic.id,
        display_name: "Synthetic Staff",
        permissions: ["appointment.read", "patient.read", "report.read", "admin.analytics.read", "website.read", "notification.read", "queue.read", "lead.read", "billing.read"],
      };
    } else if (path.endsWith("/notifications")) {
      data = [];
    } else if (path.includes("/reporting-summary")) {
      data = reportSummary;
    } else if (path.includes("/analytics/daily")) {
      data = dailyData;
    } else if (path.includes("/analytics/channels")) {
      data = channelData;
    } else if (path.includes("/analytics/funnel")) {
      data = funnelData;
    } else if (path.includes("/analytics/top-services")) {
      data = topServiceData;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data, meta: { request_id: "00000000-0000-0000-0000-000000000099" } }),
    });
  });
}

test.describe("analytics page", () => {
  test.beforeEach(async ({ page }) => {
    await installAnalyticsApi(page);
  });

  test("renders KPI cards with correct totals", async ({ page }) => {
    await page.goto("/analytics");
    // APPOINTMENTS total (15 + 10) is the hero card; the rate cards are .analytics-card.
    await expect(page.locator(".report-hero-card").first()).toContainText("APPOINTMENTS");
    await expect(page.locator(".report-hero-card").first()).toContainText("25");
    await expect(page.locator(".analytics-card")).toHaveCount(3);
    await expect(page.locator(".analytics-card").first()).toContainText("PATIENT");
  });

  test("renders bar chart with correct number of bars", async ({ page }) => {
    await page.goto("/analytics");
    await expect(page.locator(".chart-bar")).toHaveCount(dailyData.length);
  });

  test("renders funnel stages in pipeline order", async ({ page }) => {
    await page.goto("/analytics");
    const labels = page.locator(".funnel-label");
    await expect(labels).toHaveCount(6);
    await expect(labels.nth(0)).toHaveText("New");
    await expect(labels.nth(1)).toHaveText("Contacted");
    await expect(labels.nth(5)).toHaveText("Converted");
  });

  test("renders donut chart with channel labels", async ({ page }) => {
    await page.goto("/analytics");
    const legend = page.locator(".donut-legend span");
    await expect(legend).toHaveCount(3);
    await expect(legend.first()).toContainText("google");
  });

  test("renders top services table", async ({ page }) => {
    await page.goto("/analytics");
    const rows = page.locator(".invoice-row");
    await expect(rows).toHaveCount(3);
    await expect(rows.first()).toContainText("Dental cleaning");
  });

  test("range toggle re-fetches data", async ({ page }) => {
    let fetchCount = 0;
    page.on("request", (req) => {
      if (req.url().includes("/analytics/daily")) fetchCount++;
    });
    await page.goto("/analytics");
    await page.waitForSelector(".analytics-card");
    const initialCount = fetchCount;
    await page.getByLabel("Window").selectOption("7");
    await expect.poll(() => fetchCount).toBeGreaterThan(initialCount);
  });
});
