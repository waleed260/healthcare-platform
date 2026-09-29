import { test, expect } from "./fixtures";
import type { Page, Route } from "@playwright/test";

const day = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
const catalog = { clinic: { name: "Synthetic Care Clinic", timezone: "UTC" }, branches: [{ id: "branch-a", name: "Synthetic Main", address: null, timezone: "UTC" }], services: [{ id: "service-a", name: "Synthetic consultation", short_description: null, duration_minutes: 30, branch_id: "branch-a" }], doctors: [{ id: "doctor-a", public_name: "Dr. Synthetic", specialty: "General care", branch_id: "branch-a", service_id: "service-a" }] };

async function installBookingApi(page: Page, submit: Function): Promise<void> {
  await page.route("**/api/v1/public/catalog**", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: catalog }) }));
  await page.route("**/api/v1/public/availability**", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { slots: [`${day}T09:00:00Z`] } }) }));
  await submit(page);
}

test("two simultaneous requests for one doctor slot produce one booking and one APPOINTMENT_CONFLICT", async ({ browser }) => {
  const context = await browser.newContext();
  const first = await context.newPage();
  const second = await context.newPage();
  let attempts = 0;
  let winner: Page | null = null;
  const pages = [first, second];
  for (const page of pages) {
    await installBookingApi(page, async (target: Page) => {
      await target.route("**/api/v1/public/bookings", async (route: Route) => {
        attempts += 1;
        if (attempts === 1) { winner = target; return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ data: { reference: "SYN-BOOK-001", status: "pending", management_secret: "synthetic-secret" } }) }); }
        return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: { code: "APPOINTMENT_CONFLICT", message: "APPOINTMENT_CONFLICT: The selected time is no longer available." } }) });
      });
    });
  }
  await Promise.all(pages.map((page, index) => page.goto("/book/synthetic-care").then(async () => {
    await page.getByLabel("Date").fill(day);
    await page.locator(".slot").click();
    await page.getByLabel("Full name").fill(`Synthetic Booker ${index + 1}`);
    await page.getByRole("button", { name: /request appointment/i }).click();
  })));
  expect(winner).not.toBeNull();
  const loser = pages.find((page) => page !== winner);
  await expect(winner!.getByRole("heading", { name: /you.re on the list/i })).toBeVisible();
  await expect(loser!.locator(".booking-alert")).toContainText("APPOINTMENT_CONFLICT");
  expect(attempts).toBe(2);
  await context.close();
});
