import { test, expect } from "./fixtures";
import type { Page, Route } from "@playwright/test";

/**
 * Lead -> Book Appointment browser flow (the gap lead-timeline.spec.ts does NOT cover).
 *
 * These specs drive the REAL production pages and the REAL six-step appointment drawer -- no
 * component mocking, no bypassing the UI, no manual React state. Only the API is mocked at the
 * network boundary with Playwright routing, following the repo's mock-by-default convention, so
 * the assertions are about the actual frontend request code, validation, navigation and refresh.
 * The backend lifecycle itself is covered by apps/api/tests/test_lead_lifecycle_integration.py.
 */

const LEAD_ID = "11111111-1111-4111-8111-111111111111";
const BRANCH_ID = "22222222-2222-4222-8222-222222222222";
const DOCTOR_ID = "33333333-3333-4333-8333-333333333333";
const SERVICE_ID = "44444444-4444-4444-8444-444444444444";

type BookOutcome = "success" | "conflict";

type MockState = {
  booked: boolean;
  appointmentPosts: Array<Record<string, unknown>>;
  leadPatches: Array<Record<string, unknown>>;
  outcome: BookOutcome;
};

function qualifiedLead(status: string) {
  return {
    id: LEAD_ID, full_name: "Qualified Prospect", normalized_email: "prospect@example.test",
    normalized_phone: "+923001234567", source: "referral", capture_method: "manual_staff_entry",
    campaign: null, status, specialty_id: null, requested_service_id: null, branch_id: null,
    assigned_to_user_id: null, converted_to_patient_id: null, lost_reason: null, notes: null,
    created_at: "2026-10-03T08:00:00.000Z", updated_at: "2026-10-03T08:00:00.000Z", version: 1,
  };
}

const BRANCH = { id: BRANCH_ID, name: "Main Branch" };
const DOCTOR = { id: DOCTOR_ID, name: "Dr. Synthetic", public_name: "Dr. Synthetic" };
const SERVICE = { id: SERVICE_ID, name: "Consultation" };

async function installRoutes(page: Page, state: MockState, opts: { session: Record<string, unknown> }) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;
    const json = (data: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ data, meta: { next_cursor: null, request_id: "test" } }) });

    // --- specific nested paths first ---
    if (path.endsWith("/auth/me")) return json(opts.session);
    if (/\/branches\/[^/]+\/services$/.test(path)) return json([SERVICE]);
    if (/\/branches\/[^/]+\/doctors$/.test(path)) return json([DOCTOR]);
    if (/\/doctors\/[0-9a-f-]+$/.test(path)) return json({ id: DOCTOR_ID, services: [{ id: SERVICE_ID }] });
    if (/\/patients\/[0-9a-f-]+$/.test(path)) return json({ id: "p", full_name: "x", normalized_phone: "+923001234567", version: 1 });
    if (/\/appointments\/availability$/.test(path)) return json([]);
    if (/\/leads\/[^/]+\/appointments$/.test(path)) return json(state.booked ? [{ id: "appt-1", reference: "BK-TEST", branch_id: BRANCH_ID, service_id: SERVICE_ID, patient_id: "p", status: "confirmed", starts_at: "2026-10-10T10:30:00.000Z", created_at: "2026-10-03T09:00:00.000Z" }] : []);
    if (/\/leads\/[^/]+\/follow-ups$/.test(path)) return json([]);
    if (/\/leads\/[^/]+\/history$/.test(path)) return json(state.booked ? [{ id: "h1", from_status: "qualified", to_status: "appointment_booked", actor_user_id: null, reason: "appointment booked", created_at: "2026-10-03T09:00:00.000Z" }] : [{ id: "h0", from_status: null, to_status: "qualified", actor_user_id: null, reason: "lead created", created_at: "2026-10-03T08:00:00.000Z" }]);
    if (/\/leads\/[^/]+\/activities$/.test(path)) return json([]);

    // --- appointment creation (the request under test) ---
    if (path.endsWith("/appointments") && method === "POST") {
      state.appointmentPosts.push(JSON.parse(request.postData() ?? "{}"));
      if (state.outcome === "conflict") {
        return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: { code: "APPOINTMENT_CONFLICT", message: "The selected time is no longer available.", fields: null } }) });
      }
      state.booked = true;
      return json({ reference: "BK-TEST", token_number: 7, starts_at: "2026-10-10T10:30:00.000Z" }, 201);
    }
    if (path.endsWith("/appointments") && method === "GET") return json([]);

    // --- single lead (GET detail, or a PATCH we must prove never forces the stage) ---
    if (/\/leads\/[0-9a-f-]+$/.test(path)) {
      if (method === "PATCH") { state.leadPatches.push(JSON.parse(request.postData() ?? "{}")); return json(qualifiedLead(state.booked ? "appointment_booked" : "qualified")); }
      return json(qualifiedLead(state.booked ? "appointment_booked" : "qualified"));
    }
    if (path.endsWith("/leads")) return json([qualifiedLead(state.booked ? "appointment_booked" : "qualified")]);

    // --- drawer + page reference data ---
    if (path.endsWith("/branches")) return json([BRANCH]);
    if (path.endsWith("/doctors")) return json([DOCTOR]);
    if (path.endsWith("/services")) return json([SERVICE]);
    if (path.endsWith("/patients")) return json([]);
    if (path.endsWith("/specialties")) return json([]);
    if (path.endsWith("/staff/users")) return json([]);
    return json([]);
  });
}

/** Drive the shared six-step drawer. Assumes the drawer is already open on step 1.
 * Scoped to the dialog so page-level controls (e.g. the schedule page's own Branch filter)
 * never collide with the drawer's controls. */
async function completeDrawer(page: Page, patient: "lead-seeded" | "new") {
  const drawer = page.getByRole("dialog", { name: "Book appointment" });
  // Step 1 — branch + doctor
  await drawer.getByLabel("Branch").selectOption(BRANCH_ID);
  await drawer.getByRole("button", { name: "Dr. Synthetic" }).click();
  await drawer.getByRole("button", { name: /^Next/ }).click();
  // Step 2 — appointment type (Day is the default)
  await drawer.getByRole("button", { name: /^Next/ }).click();
  // Step 3 — service, then a custom time (availability mocked empty)
  await drawer.getByRole("button", { name: "Consultation" }).click();
  await drawer.getByLabel("Custom time").fill("10:30");
  await drawer.getByRole("button", { name: /^Next/ }).click();
  // Step 4 — patient
  if (patient === "new") {
    await drawer.getByRole("button", { name: "New patient" }).click();
    await drawer.getByLabel("Full name").fill("Walk-in Patient");
    await drawer.getByLabel(/Phone/).first().fill("+923009998888");
  }
  // (lead-seeded: new-patient fields are already prefilled from the lead)
  await drawer.getByRole("button", { name: /^Next/ }).click();
  // Step 5 — confirm
  await drawer.getByRole("button", { name: /Confirm booking/ }).click();
}

test.describe("Lead -> Appointment booking", () => {
  const session = { clinic_id: "clinic-synthetic", clinic_slug: "synthetic", permissions: ["lead.read", "lead.manage", "appointment.create"] };

  test("Test A: booking from a lead sends the exact lead_id and advances the lead on refetch", async ({ page }) => {
    const state: MockState = { booked: false, appointmentPosts: [], leadPatches: [], outcome: "success" };
    await installRoutes(page, state, { session });

    await page.goto("/leads");
    // Book Appointment is the lead-row action, not the drawer title.
    await page.getByRole("button", { name: /Book appointment/ }).click();
    await expect(page.getByText("STEP 1 — BRANCH & DOCTOR")).toBeVisible();

    await completeDrawer(page, "lead-seeded");

    // On the leads page a successful booking closes the drawer (onCreated) and refetches the
    // list, which then shows the server-reported stage. Waiting on the badge proves the refetch.
    await expect(page.locator(".pipeline-status.status-appointment_booked").first()).toBeVisible();
    await expect(page.getByText("STEP 1 — BRANCH & DOCTOR")).toHaveCount(0); // drawer closed

    // The outgoing request carried the original lead_id exactly once, not a patient id.
    expect(state.appointmentPosts).toHaveLength(1);
    const body = state.appointmentPosts[0];
    expect(body.lead_id).toBe(LEAD_ID);
    expect(body.patient_id).toBeUndefined();
    expect(body.full_name).toBe("Qualified Prospect");
    // The stage came from the server GET, never from a frontend status PATCH.
    expect(state.leadPatches.filter((p) => p.status === "appointment_booked" || p.status === "visited")).toHaveLength(0);

    // The lead detail shows the new appointment in its history (server data, after refresh).
    await page.goto(`/leads/${LEAD_ID}`);
    await expect(page.getByText("Linked appointments")).toBeVisible();
    await expect(page.getByText("BK-TEST")).toBeVisible();
    await expect(page.locator(".pipeline-status.status-appointment_booked").first()).toBeVisible();
  });

  test("Test B: a booking failure shows an error and never reports a false success", async ({ page }) => {
    const state: MockState = { booked: false, appointmentPosts: [], leadPatches: [], outcome: "conflict" };
    await installRoutes(page, state, { session });

    await page.goto("/leads");
    await page.getByRole("button", { name: /Book appointment/ }).click();
    await completeDrawer(page, "lead-seeded");

    // Error surfaced; no success screen (the <h2>, not the list's "Appointment Booked" filter
    // tab); still on the confirm step so the user can retry.
    await expect(page.locator(".toast-message")).toContainText("no longer available");
    await expect(page.getByRole("heading", { name: "Appointment Booked" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Confirm booking/ })).toBeVisible();
    expect(state.appointmentPosts).toHaveLength(1);
    expect(state.booked).toBe(false);
  });

  test("Test C: a non-lead booking from the schedule page omits lead_id", async ({ page }) => {
    const state: MockState = { booked: false, appointmentPosts: [], leadPatches: [], outcome: "success" };
    await installRoutes(page, state, { session });

    await page.goto("/schedule");
    await page.getByRole("button", { name: /Add appointment/ }).click();
    await expect(page.getByText("STEP 1 — BRANCH & DOCTOR")).toBeVisible();
    await completeDrawer(page, "new");

    // The schedule page keeps the drawer open, so its real success screen renders.
    await expect(page.getByRole("heading", { name: "Appointment Booked" })).toBeVisible();
    expect(state.appointmentPosts).toHaveLength(1);
    expect(state.appointmentPosts[0].lead_id).toBeUndefined();
  });
});
