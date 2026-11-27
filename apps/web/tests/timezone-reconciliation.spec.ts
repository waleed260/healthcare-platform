import { test, expect } from "./fixtures";

const permissions = ["appointment.read", "patient.read", "billing.read", "website.read", "queue.read", "lead.read", "clinical.read", "report.read", "notification.read"];

// The schedule opens on the current week, so fixtures must be dated in it — fixed dates
// stop rendering as soon as their week passes.
const today = new Date();
const slotAt = (hour: number, minute = 0) => new Date(today.getFullYear(), today.getMonth(), today.getDate(), hour, minute).toISOString();

function installApi(page: import("@playwright/test").Page, timezone = "America/New_York") {
  return page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];

    if (path.endsWith("/auth/me")) {
      data = { user_id: "u1", clinic_id: "c1", display_name: "Staff", permissions };
    } else if (path.endsWith("/notifications")) {
      data = [];
    } else if (path.endsWith("/branches")) {
      data = [{ id: "b1", name: "Main", timezone }];
    } else if (path.endsWith("/doctors")) {
      data = [{ id: "d1", public_name: "Dr. Test" }];
    } else if (path.endsWith("/services")) {
      data = [{ id: "s1", name: "Consultation" }];
    } else if (path.endsWith("/operations/dashboard-summary")) {
      data = { today_appointments: 5, pending_approvals: 2, followups_due: 20, waiting_patients: 3, no_shows: 1 };
    } else if (path.endsWith("/appointments")) {
      data = [
        { id: "a1", reference: "SYN-0001", patient_name: "Jane Doe", service_name: "Consultation", doctor_name: "Dr. Test", branch_name: "Main", starts_at: slotAt(14), ends_at: slotAt(14, 30), duration_minutes: 30, status: "confirmed" },
        { id: "a2", reference: "SYN-0002", patient_name: "John Smith", service_name: "Consultation", doctor_name: "Dr. Test", branch_name: "Main", starts_at: slotAt(15), ends_at: slotAt(15, 30), duration_minutes: 30, status: "confirmed" },
      ];
    }

    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
  });
}

test.describe("timezone reconciliation", () => {
  test("dashboard loads metrics without timezone errors", async ({ page }) => {
    await installApi(page, "America/New_York");
    await page.goto("/dashboard");
    await expect(page.locator(".kpi-card", { hasText: "Appointments" })).toContainText("5");
    await expect(page.locator(".kpi-card", { hasText: "Follow-ups" })).toContainText("20");
  });

  test("schedule page renders appointments in clinic timezone", async ({ page }) => {
    await installApi(page, "America/New_York");
    await page.goto("/schedule");
    await expect(page.getByText("Jane Doe")).toBeVisible();
    await expect(page.getByText("John Smith")).toBeVisible();
  });

  test("UTC timezone renders without conversion errors", async ({ page }) => {
    await installApi(page, "UTC");
    await page.goto("/dashboard");
    await expect(page.locator(".kpi-card", { hasText: "Appointments" })).toContainText("5");
  });

  test("Asia timezone offset renders correctly", async ({ page }) => {
    await installApi(page, "Asia/Dubai");
    await page.goto("/schedule");
    await expect(page.getByText("Jane Doe")).toBeVisible();
  });
});
