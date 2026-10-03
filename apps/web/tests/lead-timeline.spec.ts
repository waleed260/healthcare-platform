import { test, expect } from "./fixtures";

// Remediation M2 + L1: the lead-activity timeline UI and leads-list pagination.

type MockLead = { id: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; source: string; campaign: null; status: string; specialty_id: string | null; assigned_to_user_id: null; converted_to_patient_id: null; lost_reason: null; created_at: string; version: number };
type MockActivity = { id: string; lead_id: string; actor_user_id: string; kind: string; body: string; due_at: string | null; created_at: string };

const permissions = ["lead.read", "lead.manage"];

test("a lead's call and follow-up appear in the timeline, newest first", async ({ page }) => {
  const leads: MockLead[] = [];
  const activities: MockActivity[] = [];
  let seq = 0;

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let data: unknown = [];
    let status = 200;
    let nextCursor: string | null = null;

    if (path.endsWith("/auth/me")) data = { clinic_id: "clinic-synthetic", permissions };
    else if (path.endsWith("/specialties")) data = [];
    else if (/\/leads\/[^/]+\/activities$/.test(path)) {
      const leadId = path.split("/").slice(-2)[0];
      if (method === "POST") {
        const body = JSON.parse(request.postData() ?? "{}");
        seq += 1;
        const activity: MockActivity = { id: `act-${seq}`, lead_id: leadId, actor_user_id: "user-1", kind: body.kind, body: body.body, due_at: body.due_at ?? null, created_at: new Date(Date.UTC(2026, 9, 3, 9, 0, seq)).toISOString() };
        activities.push(activity);
        data = activity; status = 201;
      } else {
        data = [...activities].sort((a, b) => b.created_at.localeCompare(a.created_at));
      }
    } else if (path.endsWith("/leads")) {
      if (method === "POST") {
        const body = JSON.parse(request.postData() ?? "{}");
        const lead: MockLead = { id: "lead-1", full_name: body.full_name, normalized_email: body.email ?? null, normalized_phone: body.phone ?? null, source: body.source, campaign: null, status: "new", specialty_id: body.specialty_id ?? null, assigned_to_user_id: null, converted_to_patient_id: null, lost_reason: null, created_at: new Date(Date.UTC(2026, 9, 3, 8, 0, 0)).toISOString(), version: 1 };
        leads.push(lead);
        data = lead; status = 201;
      } else {
        data = leads;
      }
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ data, meta: { next_cursor: nextCursor } }) });
  });

  await page.goto("/leads");

  // Create a lead.
  await page.getByRole("button", { name: /new lead/i }).click();
  await page.getByLabel("Full name").fill("Prospect Zero");
  await page.getByRole("button", { name: /add lead/i }).click();
  await expect(page.getByRole("heading", { name: "Prospect Zero" })).toBeVisible();

  // Open its timeline.
  await page.getByRole("button", { name: /^Timeline/ }).click();
  await expect(page.getByText(/no activity yet/i)).toBeVisible();

  // Add a call.
  await page.getByLabel("Type").selectOption("call");
  await page.getByLabel("Detail").fill("Called the prospect");
  await page.getByRole("button", { name: /^Add/ }).click();
  await expect(page.locator(".activity-item")).toHaveCount(1);

  // Add a follow-up with a due date.
  await page.getByLabel("Type").selectOption("follow_up");
  await page.getByLabel("Detail").fill("Schedule follow-up");
  await page.getByLabel("Due").fill("2026-10-10T09:00");
  await page.getByRole("button", { name: /^Add/ }).click();

  const items = page.locator(".activity-item");
  await expect(items).toHaveCount(2);
  // Newest first: the follow-up precedes the earlier call.
  await expect(items.nth(0)).toContainText("Schedule follow-up");
  await expect(items.nth(0)).toContainText(/due/i);
  await expect(items.nth(1)).toContainText("Called the prospect");
});

test("the leads list loads the next page on a >100-lead fixture", async ({ page }) => {
  const firstPage: MockLead[] = Array.from({ length: 100 }, (_, index) => ({ id: `lead-${index}`, full_name: `Synthetic Lead ${index}`, normalized_email: null, normalized_phone: null, source: "website", campaign: null, status: "new", specialty_id: null, assigned_to_user_id: null, converted_to_patient_id: null, lost_reason: null, created_at: new Date(Date.UTC(2026, 9, 3, 8, 0, 0)).toISOString(), version: 1 }));
  const secondPage: MockLead[] = Array.from({ length: 20 }, (_, index) => ({ id: `lead-${100 + index}`, full_name: `Synthetic Lead ${100 + index}`, normalized_email: null, normalized_phone: null, source: "website", campaign: null, status: "new", specialty_id: null, assigned_to_user_id: null, converted_to_patient_id: null, lost_reason: null, created_at: new Date(Date.UTC(2026, 9, 2, 8, 0, 0)).toISOString(), version: 1 }));

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    let data: unknown = [];
    let nextCursor: string | null = null;
    if (path.endsWith("/auth/me")) data = { clinic_id: "clinic-synthetic", permissions };
    else if (path.endsWith("/specialties")) data = [];
    else if (path.endsWith("/leads")) {
      if (url.searchParams.get("cursor") === "page-2") { data = secondPage; nextCursor = null; }
      else { data = firstPage; nextCursor = "page-2"; }
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { next_cursor: nextCursor } }) });
  });

  await page.goto("/leads");
  await expect(page.locator(".lead-row")).toHaveCount(100);
  await page.getByRole("button", { name: /load more leads/i }).click();
  await expect(page.locator(".lead-row")).toHaveCount(120);
  // The button disappears once the final page has no further cursor.
  await expect(page.getByRole("button", { name: /load more leads/i })).toHaveCount(0);
});
