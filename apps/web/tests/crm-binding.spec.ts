import { test, expect } from "./fixtures";

const permissions = ["appointment.read", "patient.read", "billing.read", "website.read", "website.edit", "website.publish", "queue.read", "lead.read", "clinical.read", "report.read", "notification.read"];

test.describe("CRM-to-website data binding", () => {
  function installApi(page: import("@playwright/test").Page, serviceName = "Consultation") {
    return page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];

      if (path.endsWith("/auth/me")) {
        data = { user_id: "u1", clinic_id: "c1", display_name: "Admin", permissions };
      } else if (path.endsWith("/notifications")) {
        data = [];
      } else if (path.endsWith("/branches")) {
        data = [{ id: "b1", name: "Main Branch", address: "123 Main St" }];
      } else if (path.endsWith("/services")) {
        data = [{ id: "s1", name: serviceName, short_description: "General checkup", duration_minutes: 30, price_minor: 5000, branch_id: "b1" }];
      } else if (path.endsWith("/doctors")) {
        data = [{ id: "d1", public_name: "Dr. Smith", specialty: "General", branch_id: "b1" }];
      } else if (path.includes("/public/catalog")) {
        data = {
          clinic: { name: "Test Clinic", timezone: "UTC" },
          branches: [{ id: "b1", name: "Main Branch", address: "123 Main St", timezone: "UTC" }],
          services: [{ id: "s1", name: serviceName, short_description: "General checkup", duration_minutes: 30, branch_id: "b1" }],
          doctors: [{ id: "d1", public_name: "Dr. Smith", specialty: "General", branch_id: "b1", service_id: "s1" }],
        };
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
    });
  }

  test("service name from CRM appears on booking page", async ({ page }) => {
    await installApi(page, "Teeth Cleaning");
    await page.goto("/book/test-clinic");
    await expect(page.getByText("Teeth Cleaning")).toBeVisible();
  });

  test("updated service name propagates to booking", async ({ page }) => {
    await installApi(page, "Root Canal Treatment");
    await page.goto("/book/test-clinic");
    await expect(page.getByText("Root Canal Treatment")).toBeVisible();
  });

  test("doctor name from CRM appears on booking page", async ({ page }) => {
    await installApi(page);
    await page.goto("/book/test-clinic");
    await expect(page.getByText("Dr. Smith")).toBeVisible();
  });

  test("branch info from CRM appears on booking page", async ({ page }) => {
    await installApi(page);
    await page.goto("/book/test-clinic");
    await expect(page.getByText("Main Branch")).toBeVisible();
  });
});
