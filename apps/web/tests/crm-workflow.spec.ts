import { test, expect } from "./fixtures";

const permissions = ["patient.read", "patient.write", "appointment.read", "appointment.create", "appointment.approve", "appointment.check_in", "appointment.manage", "queue.read", "queue.manage", "clinical.read"];

test.describe("CRM workflow: patient → appointment → consultation", () => {
  test.beforeEach(async ({ page }) => {
    let patientCreated = false;
    let appointmentStatus = "requested";

    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      let data: unknown = [];

      if (path.endsWith("/auth/me")) {
        data = { user_id: "u1", clinic_id: "c1", display_name: "Staff", permissions, clinic_slug: "demo" };
      } else if (path.endsWith("/notifications")) {
        data = [];
      } else if (path.endsWith("/patients") && method === "POST") {
        patientCreated = true;
        data = { id: "p1", full_name: "Test Patient", patient_number: "PT-001", status: "active", version: 1 };
      } else if (path.endsWith("/patients") && method === "GET") {
        data = patientCreated ? [{ id: "p1", full_name: "Test Patient", patient_number: "PT-001", normalized_email: "test@example.com", normalized_phone: null, status: "active", version: 1 }] : [];
      } else if (path.includes("/patients/p1") && !path.includes("/")) {
        data = { id: "p1", full_name: "Test Patient", patient_number: "PT-001", status: "active", version: 1, timeline: [] };
      } else if (path.endsWith("/appointments") && method === "POST") {
        data = { id: "a1", reference: "APT-001", branch_id: "b1", doctor_id: null, service_id: "s1", patient_id: "p1", starts_at: "2026-10-08T09:00:00Z", ends_at: "2026-10-08T09:30:00Z", status: "requested", version: 1 };
      } else if (path.endsWith("/appointments") && method === "GET") {
        data = appointmentStatus !== "requested" || patientCreated ? [{ id: "a1", reference: "APT-001", branch_id: "b1", doctor_id: null, service_id: "s1", patient_id: "p1", starts_at: "2026-10-08T09:00:00Z", ends_at: "2026-10-08T09:30:00Z", status: appointmentStatus, version: 1 }] : [];
      } else if (path.endsWith("/approve")) {
        appointmentStatus = "confirmed";
        data = { status: "confirmed", version: 2 };
      } else if (path.endsWith("/transitions")) {
        appointmentStatus = "arrived";
        data = { status: "arrived", version: 3 };
      } else if (path.endsWith("/branches")) {
        data = [{ id: "b1", name: "Main Branch" }];
      } else if (path.endsWith("/doctors")) {
        data = [{ id: "d1", public_name: "Dr. Test" }];
      } else if (path.endsWith("/services")) {
        data = [{ id: "s1", name: "Consultation" }];
      } else if (path.endsWith("/operations/queue")) {
        data = appointmentStatus === "arrived" ? [{ id: "q1", appointment_id: "a1", status: "waiting", checked_in_at: "2026-10-08T08:55:00Z", priority: 0, full_name: "Test Patient", reference: "APT-001", starts_at: "2026-10-08T09:00:00Z", version: 1 }] : [];
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
    });
  });

  test("patient list loads with correct structure", async ({ page }) => {
    await page.goto("/patients");
    await expect(page.locator(".dash-topline")).toBeVisible();
  });

  test("schedule page renders calendar grid", async ({ page }) => {
    await page.goto("/schedule");
    await expect(page.locator(".calendar-grid")).toBeVisible();
    await expect(page.locator(".calendar-toolbar")).toBeVisible();
  });

  test("schedule page shows view switcher with day/week/month", async ({ page }) => {
    await page.goto("/schedule");
    await expect(page.locator(".view-switcher")).toBeVisible();
    await expect(page.locator(".view-switcher button")).toHaveCount(3);
  });

  test("queue page renders without dashboard wrapper", async ({ page }) => {
    await page.goto("/queue");
    await expect(page.locator(".dash-content.queue-content")).toBeVisible();
    await expect(page.locator(".dashboard-page")).toHaveCount(0);
  });
});
