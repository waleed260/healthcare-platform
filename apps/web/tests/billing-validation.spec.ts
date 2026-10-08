import { test, expect } from "./fixtures";

const permissions = ["billing.read", "billing.write", "patient.read", "appointment.read", "invoice.write", "invoice.read"];

test.describe("billing validation", () => {
  test.beforeEach(async ({ page }) => {
    let invoiceStatus = "draft";

    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      let data: unknown = [];

      if (path.endsWith("/auth/me")) {
        data = { user_id: "u1", clinic_id: "c1", display_name: "Staff", permissions };
      } else if (path.endsWith("/notifications")) {
        data = [];
      } else if (path.endsWith("/invoices") && method === "GET") {
        data = [{ id: "inv-1", invoice_number: "INV-001", patient_id: "p1", patient_name: "Test Patient", appointment_id: "a1", status: invoiceStatus, total_minor: 15000, paid_minor: invoiceStatus === "paid" ? 15000 : 0, currency: "USD", lines: [{ id: "li-1", service_id: "s1", description: "Consultation", quantity: 1, unit_price_minor: 15000, line_total_minor: 15000 }], version: 1, created_at: "2026-10-07T10:00:00Z" }];
      } else if (path.includes("/invoices/") && method === "GET") {
        data = { id: "inv-1", invoice_number: "INV-001", patient_id: "p1", patient_name: "Test Patient", status: invoiceStatus, total_minor: 15000, paid_minor: invoiceStatus === "paid" ? 15000 : 0, currency: "USD", lines: [{ id: "li-1", service_id: "s1", description: "Consultation", quantity: 1, unit_price_minor: 15000, line_total_minor: 15000 }], version: 1 };
      } else if (path.includes("/finalize")) {
        invoiceStatus = "finalized";
        data = { status: "finalized", version: 2 };
      } else if (path.includes("/payments") && method === "POST") {
        invoiceStatus = "paid";
        data = { id: "pay-1", amount_minor: 15000, method: "card" };
      } else if (path.includes("/refund")) {
        invoiceStatus = "refunded";
        data = { id: "ref-1", amount_minor: 15000 };
      } else if (path.endsWith("/patients")) {
        data = [{ id: "p1", full_name: "Test Patient", patient_number: "PT-001" }];
      } else if (path.endsWith("/appointments")) {
        data = [{ id: "a1", reference: "APT-001", starts_at: "2026-10-08T09:00:00Z", status: "completed" }];
      } else if (path.endsWith("/services")) {
        data = [{ id: "s1", name: "Consultation", base_price_minor: 15000, currency: "USD" }];
      } else if (path.endsWith("/branches")) {
        data = [{ id: "b1", name: "Main" }];
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1" } }) });
    });
  });

  test("billing page renders invoice list", async ({ page }) => {
    await page.goto("/billing");
    await expect(page.locator(".invoice-row")).toHaveCount(1);
    await expect(page.locator(".invoice-row").first()).toContainText("INV-001");
  });

  test("invoice shows correct total", async ({ page }) => {
    await page.goto("/billing");
    await expect(page.locator(".invoice-row").first()).toContainText("150");
  });

  test("billing page has create invoice button", async ({ page }) => {
    await page.goto("/billing");
    const btn = page.getByRole("button", { name: /new invoice|create/i });
    await expect(btn).toBeVisible();
  });
});
