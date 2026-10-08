import { test, expect } from "./fixtures";

test.describe("public booking flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      let data: unknown = [];

      if (path.includes("/public/catalog")) {
        data = {
          clinic: { name: "Demo Clinic", timezone: "UTC" },
          branches: [
            { id: "b1", name: "Main", address: { street: "123 Test St" }, timezone: "UTC" },
            { id: "b2", name: "North", address: { street: "456 North Ave" }, timezone: "UTC" },
          ],
          services: [
            { id: "s1", name: "Consultation", short_description: "General checkup", duration_minutes: 30, branch_id: "b1", price_minor: 5000 },
            { id: "s2", name: "Teeth Cleaning", short_description: "Professional cleaning", duration_minutes: 45, branch_id: "b1", price_minor: 7500 },
            { id: "s3", name: "Skin Assessment", short_description: "Dermatology assessment", duration_minutes: 60, branch_id: "b2", price_minor: 10000 },
          ],
          doctors: [
            { id: "d1", public_name: "Dr. Demo", specialty: "General", branch_id: "b1", service_id: "s1" },
            { id: "d2", public_name: "Dr. Smith", specialty: "Dentistry", branch_id: "b1", service_id: "s2" },
          ],
        };
      } else if (path.includes("/public/availability")) {
        data = { slots: ["2026-10-10T09:00:00Z", "2026-10-10T10:00:00Z", "2026-10-10T11:00:00Z"] };
      } else if (path.includes("/public/bookings") && method === "POST") {
        data = { reference: "BK-001", status: "pending", management_secret: "secret-abc" };
        await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
        return;
      } else if (path.includes("/public/sites/slug")) {
        data = { snapshot: { template_key: "calm_clinic", brand: {}, pages: [{ slug: "home", title: "Demo Clinic", sections: [{ id: "s1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Welcome", body: "Book your visit" }, is_visible: true }] }] } };
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
    });
  });

  test("booking page renders service selection", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await expect(page.getByText("Consultation")).toBeVisible();
  });

  test("booking page shows clinic name", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await expect(page.getByText("Demo Clinic")).toBeVisible();
  });

  test("step indicator shows all 5 steps", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await expect(page.locator(".booking-step-dot")).toHaveCount(5);
    await expect(page.getByText("Service")).toBeVisible();
    await expect(page.getByText("Provider")).toBeVisible();
    await expect(page.getByText("Confirm")).toBeVisible();
  });

  test("selecting a service enables next button", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await expect(page.getByRole("button", { name: /next/i })).toBeEnabled();
  });

  test("provider step shows available doctors", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await page.getByRole("button", { name: /next/i }).click();
    await expect(page.getByText("Dr. Demo")).toBeVisible();
    await expect(page.getByText("Any available")).toBeVisible();
  });

  test("booking page shows available time slots on date step", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.getByRole("button", { name: /next/i }).click();
    await expect(page.locator(".slot")).toHaveCount(3);
  });

  test("back button navigates to previous step", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await page.getByRole("button", { name: /next/i }).click();
    await expect(page.getByText("Dr. Demo")).toBeVisible();
    await page.getByRole("button", { name: /back/i }).click();
    await expect(page.getByText("Consultation")).toBeVisible();
  });

  test("details step collects patient information", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.locator(".slot").first().click();
    await page.getByRole("button", { name: /next/i }).click();
    await expect(page.getByLabel(/full name/i)).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/phone/i)).toBeVisible();
  });

  test("confirmation step shows booking summary", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.locator(".slot").first().click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.getByLabel(/full name/i).fill("Test Patient");
    await page.getByRole("button", { name: /next/i }).click();
    await expect(page.getByText("Confirm your booking")).toBeVisible();
    await expect(page.getByText("Consultation")).toBeVisible();
    await expect(page.getByText("Test Patient")).toBeVisible();
  });

  test("successful booking shows reference number", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.locator(".slot").first().click();
    await page.getByRole("button", { name: /next/i }).click();
    await page.getByLabel(/full name/i).fill("Test Patient");
    await page.getByRole("button", { name: /next/i }).click();
    await page.getByRole("button", { name: /request appointment/i }).click();
    await expect(page.getByText("BK-001")).toBeVisible();
    await expect(page.getByText(/request received/i)).toBeVisible();
  });

  test("multi-branch clinic shows branch selector", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await expect(page.getByText("Main")).toBeVisible();
    await expect(page.getByText("North")).toBeVisible();
  });

  test("switching branch filters services", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("North").click();
    await expect(page.getByText("Skin Assessment")).toBeVisible();
  });

  test("booking page shows timezone", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await expect(page.getByText("UTC")).toBeVisible();
  });
});
