import { test, expect } from "@playwright/test";

const clinicA = { id: "clinic-a", name: "Synthetic Clinic A", slug: "synthetic-a", status: "active" };
const siteA = { id: "site-a", name: "Clinic A website", template_key: "calm_clinic", status: "draft", version: 1, draft_version_id: "version-a", live_version_id: null, brand: {} };
const pageA = { id: "page-a", slug: "home", title: "Clinic A home", version: 1 };
const sectionA = { id: "section-a", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Clinic A care", body: "Synthetic A copy." }, is_visible: true, version: 1 };

test("Clinic A staff cannot see Clinic B patients, appointments, or website", async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let status = 200;
    let data: unknown = [];
    if (path.endsWith("/auth/me")) data = { clinic_id: clinicA.id, display_name: "Synthetic A staff", permissions: ["patient.read", "appointment.read", "website.read", "website.edit"] };
    else if (path.endsWith("/patients")) data = [{ id: "patient-a", patient_number: "A-0001", full_name: "Synthetic Patient A", normalized_email: null, normalized_phone: null, status: "active", version: 1 }];
    else if (path.endsWith("/patient-b")) { status = 404; data = null; }
    else if (path.endsWith("/appointments")) data = [{ id: "appointment-a", reference: "A-0001", branch_id: "branch-a", doctor_id: null, service_id: "service-a", patient_id: "patient-a", starts_at: "2026-09-29T09:00:00Z", ends_at: "2026-09-29T09:30:00Z", status: "confirmed", version: 1 }];
    else if (path.endsWith("/websites")) data = [siteA];
    else if (path.endsWith("/websites/domains")) data = [];
    else if (path.endsWith("/pages")) data = [pageA];
    else if (path.endsWith("/versions")) data = [];
    else if (path.endsWith("/sections")) data = [sectionA];
    else if (path.endsWith("/validation")) data = { valid: true, code: null, message: null };
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(status === 404 ? { error: { message: "Patient not found in your clinic scope." } } : { data, meta: { next_cursor: null } }) });
  });

  await page.goto("/patients");
  await expect(page.getByText("Synthetic Patient A")).toBeVisible();
  await expect(page.getByText("Synthetic Patient B")).toHaveCount(0);
  await page.goto("/patients/patient-b");
  await expect(page.locator(".workspace-alert")).toContainText("Patient not found in your clinic scope.");
  await expect(page.getByText("Synthetic Patient B")).toHaveCount(0);

  await page.goto("/schedule");
  await expect(page.getByText("A-0001")).toBeVisible();
  await expect(page.getByText("B-0001")).toHaveCount(0);

  await page.goto("/website");
  await expect(page.getByRole("heading", { name: "Clinic A home" })).toBeVisible();
  await expect(page.getByText("Clinic B website")).toHaveCount(0);
});
