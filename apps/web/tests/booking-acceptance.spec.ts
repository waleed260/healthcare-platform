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
          branches: [{ id: "b1", name: "Main", address: "123 Test St", timezone: "UTC" }],
          services: [{ id: "s1", name: "Consultation", short_description: "General checkup", duration_minutes: 30, branch_id: "b1" }],
          doctors: [{ id: "d1", public_name: "Dr. Demo", specialty: "General", branch_id: "b1", service_id: "s1" }],
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

  test("booking page shows available time slots", async ({ page }) => {
    await page.goto("/book/demo-clinic");
    await page.getByText("Consultation").click();
    await expect(page.locator(".slot")).toHaveCount(3);
  });
});
