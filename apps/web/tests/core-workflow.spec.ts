import { test, expect } from "@playwright/test";

test("synthetic clinic workflow runs from onboarding through a completed consultation", async ({ page }) => {
  const bookingDay = new Date(Date.now() + 2 * 86_400_000);
  const bookingDate = bookingDay.toISOString().slice(0, 10);
  const bookingStarts = `${bookingDate}T09:00:00Z`;
  let setupCompleted = false;
  let published = false;
  let bookingCreated = false;
  let appointmentStatus: "requested" | "confirmed" | "waiting" | "in_consultation" | "completed" = "requested";
  const permissions = ["clinic.read", "clinic.update", "appointment.read", "appointment.approve", "appointment.check_in", "appointment.manage", "queue.read", "queue.manage", "website.read", "website.edit", "website.publish"];
  const website = { id: "site-1", name: "Synthetic Clinic Website", template_key: "calm_clinic", status: "draft", version: 1, draft_version_id: "version-1", live_version_id: null, brand: {} };
  const pageRecord = { id: "page-1", slug: "home", title: "Synthetic Clinic home", version: 1 };
  const section = { id: "section-1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Synthetic care", body: "Thoughtful synthetic care." }, is_visible: true, version: 1 };

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = [];
    let status = 200;
    if (path.endsWith("/auth/me")) data = { clinic_id: "clinic-synthetic", permissions };
    else if (path.endsWith("/clinic/onboarding")) data = { completed: setupCompleted, completed_at: setupCompleted ? "2026-09-27T08:00:00Z" : null, steps: { first_branch: true, branch_hours: true, doctor: true, service: true, doctor_assignment: true, service_assignment: true }, ready_to_complete: !setupCompleted };
    else if (path.endsWith("/onboarding/complete")) { setupCompleted = true; data = { completed: true }; }
    else if (path.endsWith("/websites")) data = [published ? { ...website, status: "published", version: 2, live_version_id: "version-2" } : website];
    else if (path.endsWith("/domains")) data = [];
    else if (path.endsWith("/pages")) data = [pageRecord];
    else if (path.endsWith("/versions")) data = [{ id: "version-1", version_number: 1, published_at: null, created_at: "2026-09-27T08:00:00Z" }];
    else if (path.endsWith("/sections")) data = [section];
    else if (path.endsWith("/validation")) data = { valid: true, code: null, message: null };
    else if (path.endsWith("/publish")) { published = true; data = { ...website, status: "published", version: 2, live_version_id: "version-2" }; }
    else if (path.endsWith("/public/sites/slug/synthetic-care")) data = { snapshot: { template_key: "calm_clinic", brand: {}, pages: [{ slug: "home", title: "Synthetic Clinic", sections: [{ ...section, content: { heading: "Welcome synthetic patients", body: "Book a visit." } }] }] } };
    else if (path.endsWith("/public/catalog")) data = { clinic: { name: "Synthetic Clinic", timezone: "UTC" }, branches: [{ id: "branch-1", name: "Synthetic Main", address: null, timezone: "UTC" }], services: [{ id: "service-1", name: "Synthetic consultation", short_description: null, duration_minutes: 30, branch_id: "branch-1" }], doctors: [{ id: "doctor-1", public_name: "Dr. Synthetic", specialty: "General care", branch_id: "branch-1", service_id: "service-1" }] };
    else if (path.endsWith("/public/availability")) data = { slots: [bookingStarts] };
    else if (path.endsWith("/public/bookings")) { bookingCreated = true; data = { reference: "SYN-BOOK-001", status: "pending", management_secret: "synthetic-secret" }; status = 201; }
    else if (path.endsWith("/appointments")) data = bookingCreated ? [{ id: "appointment-1", reference: "SYN-BOOK-001", branch_id: "branch-1", doctor_id: "doctor-1", service_id: "service-1", patient_id: "patient-1", starts_at: bookingStarts, ends_at: `${bookingDate}T09:30:00Z`, status: appointmentStatus, version: 1 }] : [];
    else if (path.endsWith("/approve")) { appointmentStatus = "confirmed"; data = { status: appointmentStatus, version: 2 }; }
    else if (path.endsWith("/transitions")) { appointmentStatus = "waiting"; data = { status: appointmentStatus, version: 3 }; }
    else if (path.endsWith("/operations/queue")) data = appointmentStatus === "waiting" || appointmentStatus === "in_consultation" ? [{ id: "queue-1", appointment_id: "appointment-1", status: appointmentStatus === "waiting" ? "waiting" : "in_consultation", checked_in_at: `${bookingDate}T08:55:00Z`, priority: 0, full_name: "Synthetic Patient", reference: "SYN-BOOK-001", starts_at: bookingStarts, version: appointmentStatus === "waiting" ? 1 : 2 }] : [];
    else if (path.endsWith("/start")) { appointmentStatus = "in_consultation"; data = { status: appointmentStatus, version: 2 }; }
    else if (path.endsWith("/complete")) { appointmentStatus = "completed"; data = { status: appointmentStatus, version: 3 }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ data, meta: { next_cursor: null } }) });
  });

  await page.goto("/onboarding");
  await page.getByRole("button", { name: /complete setup/i }).click();
  await expect(page.locator(".success-alert")).toContainText(/setup completed/i);

  await page.goto("/website");
  await page.getByRole("button", { name: /publish draft/i }).click();
  await expect(page.getByRole("status")).toContainText(/draft published/i);

  await page.goto("/synthetic-care");
  await expect(page.getByRole("heading", { name: /welcome synthetic patients/i })).toBeVisible();
  await page.getByRole("link", { name: /book an appointment/i }).first().click();
  await page.getByLabel("Date").fill(bookingDate);
  await page.locator(".slot").click();
  await page.getByLabel("Full name").fill("Synthetic Patient");
  await page.getByRole("button", { name: /request appointment/i }).click();
  await expect(page.getByText("SYN-BOOK-001")).toBeVisible();
  expect(bookingCreated).toBe(true);

  await page.goto("/schedule");
  await page.getByRole("button", { name: "Next period" }).click();
  await expect(page.getByText("SYN-BOOK-001")).toBeVisible();
  await page.locator(".calendar-appointment").first().click({ force: true });
  await page.getByRole("button", { name: "Approve" }).click({ force: true });
  await page.locator(".calendar-appointment").first().click({ force: true });
  await expect(page.getByRole("button", { name: "Check in" })).toBeVisible();
  await page.getByRole("button", { name: "Check in" }).click({ force: true });

  await page.goto("/queue");
  await expect(page.getByText("SYN-BOOK-001")).toBeVisible();
  await page.getByRole("button", { name: /start consultation/i }).click();
  await expect(page.getByText("in consultation")).toBeVisible();
  await page.getByRole("button", { name: "Complete" }).click();
  await expect(page.getByText("The queue is clear")).toBeVisible();
  expect(appointmentStatus).toBe("completed");
});
