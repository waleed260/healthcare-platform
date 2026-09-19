import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";

const clinic = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Synthetic Care Clinic",
  slug: "synthetic-care",
  status: "active",
  timezone: "UTC",
  locale: "en-US",
  version: 1,
};

async function installSyntheticApi(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path.endsWith("/clinic") || path.endsWith("/clinic/context")) data = clinic;
    if (path.endsWith("/clinic/onboarding")) {
      data = { completed: false, completed_at: null, steps: {}, ready_to_complete: false };
    }
    if (path.endsWith("/dashboard-summary")) {
      data = { today_appointments: 0, pending_approvals: 0, followups_due: 0 };
    }
    if (path.endsWith("/public/catalog")) {
      data = {
        clinic: { name: clinic.name, timezone: clinic.timezone },
        branches: [{ id: "branch-1", name: "Main clinic", address: null, timezone: "UTC" }],
        services: [{ id: "service-1", name: "General consultation", short_description: null, duration_minutes: 30, branch_id: "branch-1" }],
        doctors: [],
      };
    }
    if (path.endsWith("/public/availability")) data = { slots: [] };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data, meta: { request_id: "00000000-0000-0000-0000-000000000002" } }),
    });
  });
}

const coreRoutes = ["/", "/login", "/onboarding", "/dashboard", "/schedule", "/patients", "/queue", "/book/synthetic-care"];

test.describe("core responsive browser flows", () => {
  test.beforeEach(async ({ page }) => {
    await installSyntheticApi(page);
  });

  for (const route of coreRoutes) {
    test(`renders ${route} with a named main landmark`, async ({ page }) => {
      await page.goto(route);
      await expect(page.locator("main")).toHaveCount(1);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator("h1").first()).toBeVisible();
    });
  }

  test("booking is usable at a mobile breakpoint", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/book/synthetic-care");
    await expect(page.getByRole("heading", { name: /make time for/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /request appointment/i })).toBeDisabled();
  });

  test("keyboard focus is visible on the public entry flow", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
  });

  test("web responses include nonce-based security headers", async ({ page }) => {
    const response = await page.goto("/");
    expect(response).not.toBeNull();
    const headers = response?.headers() ?? {};
    expect(headers["content-security-policy"]).toContain("script-src 'self' 'nonce-");
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
  });

  test("patient directory appends the next cursor page", async ({ page }) => {
    let cursorRequests = 0;
    await page.route("**/api/v1/patients*", async (route) => {
      const hasCursor = Boolean(new URL(route.request().url()).searchParams.get("cursor"));
      if (hasCursor) cursorRequests += 1;
      const patient = hasCursor
        ? { id: "patient-2", patient_number: "SYN-0002", full_name: "Synthetic Second", normalized_email: null, normalized_phone: null, status: "active", version: 1 }
        : { id: "patient-1", patient_number: "SYN-0001", full_name: "Synthetic First", normalized_email: null, normalized_phone: null, status: "active", version: 1 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [patient], meta: { next_cursor: hasCursor ? null : "synthetic-next-cursor" } }) });
    });
    await page.goto("/patients");
    await expect(page.getByText("Synthetic First")).toBeVisible();
    await page.getByRole("button", { name: /load more patient records/i }).click();
    await expect(page.getByText("Synthetic Second")).toBeVisible();
    expect(cursorRequests).toBe(1);
    await expect(page.getByRole("button", { name: /load more patient records/i })).toHaveCount(0);
  });

  test("patient detail renders only the authorized care-team response", async ({ page }) => {
    await page.route("**/api/v1/patients/patient-1**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];
      if (path.endsWith("/care-team")) data = [{ doctor_id: "doctor-1", public_name: "Synthetic Care Doctor", specialty: "General care", created_at: "2026-01-01T09:00:00Z" }];
      else if (path.endsWith("/notes")) data = [{ id: "note-1", note_type: "care", visibility: "care_team", body: "Synthetic scoped note", created_at: "2026-01-01T09:00:00Z" }];
      else if (path.endsWith("/contacts")) data = [];
      else data = { id: "patient-1", patient_number: "SYN-0001", full_name: "Synthetic First", normalized_email: null, normalized_phone: null, date_of_birth: null, status: "active", version: 1 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "00000000-0000-0000-0000-000000000002" } }) });
    });
    await page.goto("/patients/patient-1");
    await expect(page.getByRole("heading", { name: "Assigned clinicians" })).toBeVisible();
    await expect(page.getByText("Synthetic Care Doctor")).toBeVisible();
    await expect(page.getByText("Synthetic scoped note")).toBeVisible();
  });

  test("queue appends the next cursor page", async ({ page }) => {
    let cursorRequests = 0;
    await page.route("**/api/v1/operations/queue*", async (route) => {
      const hasCursor = Boolean(new URL(route.request().url()).searchParams.get("cursor"));
      if (hasCursor) cursorRequests += 1;
      const entry = hasCursor
        ? { id: "queue-2", appointment_id: "appointment-2", status: "waiting", checked_in_at: "2026-09-16T09:01:00Z", priority: 0, full_name: "Synthetic Second", reference: "SYN-0002", starts_at: "2026-09-16T09:30:00Z", version: 1 }
        : { id: "queue-1", appointment_id: "appointment-1", status: "waiting", checked_in_at: "2026-09-16T09:00:00Z", priority: 0, full_name: "Synthetic First", reference: "SYN-0001", starts_at: "2026-09-16T09:30:00Z", version: 1 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [entry], meta: { next_cursor: hasCursor ? null : "synthetic-queue-cursor" } }) });
    });
    await page.goto("/queue");
    await expect(page.getByText("Synthetic First")).toBeVisible();
    await page.getByRole("button", { name: /load more queue entries/i }).click();
    await expect(page.getByText("Synthetic Second")).toBeVisible();
    expect(cursorRequests).toBe(1);
    await expect(page.getByRole("button", { name: /load more queue entries/i })).toHaveCount(0);
  });

  test("onboarding submits the first branch through the protected API", async ({ page }) => {
    let submitted = false;
    page.on("request", (request) => {
      if (request.url().endsWith("/api/v1/branches") && request.method() === "POST") submitted = true;
    });
    await page.goto("/onboarding");
    await page.getByLabel("Branch name").fill("Synthetic Main Clinic");
    await page.getByRole("button", { name: /save branch/i }).click();
    await expect.poll(() => submitted).toBe(true);
  });

  test("public booking submits a synthetic appointment request", async ({ page }) => {
    const bookingDay = new Date();
    bookingDay.setDate(bookingDay.getDate() + 7);
    const day = bookingDay.toISOString().slice(0, 10);
    await page.route("**/api/v1/public/availability**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { slots: [`${day}T09:00:00Z`] } }) });
    });
    await page.route("**/api/v1/public/bookings", async (route) => {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ data: { reference: "SYN-0001", status: "pending", management_secret: "synthetic-secret" } }) });
    });
    await page.goto("/book/synthetic-care");
    await page.getByLabel("Date").fill(day);
    await expect(page.locator(".slot")).toHaveCount(1);
    await page.locator(".slot").click();
    await page.getByLabel("Full name").fill("Synthetic Booking");
    await page.getByRole("button", { name: /request appointment/i }).click();
    await expect(page.getByRole("heading", { name: /you.re on the list/i })).toBeVisible();
    await expect(page.getByText("SYN-0001")).toBeVisible();
  });

  for (const route of coreRoutes) {
    test(`${route} has no automated WCAG violations`, async ({ page }) => {
      await page.goto(route);
      if (route.startsWith("/book/")) {
        await expect(page.getByRole("heading", { name: /make time for|you.re on the list/i })).toBeVisible();
      } else {
        await expect(page.locator("h1").first()).toBeVisible();
      }
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });
  }
});
