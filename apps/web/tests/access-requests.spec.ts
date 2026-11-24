import { test, expect } from "./fixtures";

// Admin reviews a pending staff access request and approves it with a chosen role;
// then the public self-service request form submits and shows a generic confirmation.
// Fully mocked (no backend), like the other browser specs.

test("admin approves a pending access request with a chosen role", async ({ page }) => {
  let approved = false;
  const permissions = ["staff.read", "staff.manage", "clinic.read"];
  const pendingRequest = { id: "req-1", email: "newbie@clinic.test", display_name: "New Bie", requested_role: "Reception", reason: "Joining the front desk team", status: "pending", decided_at: null, created_at: "2026-11-20T08:00:00Z", version: 1 };

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = [];
    let status = 200;
    if (path.endsWith("/auth/me")) data = { clinic_id: "clinic-1", user_id: "admin-1", permissions };
    else if (path.endsWith("/staff/access-requests")) data = approved ? [] : [pendingRequest];
    else if (path.endsWith(`/staff/access-requests/${pendingRequest.id}/approve`)) { approved = true; data = { status: "approved", setup_url: "https://example.test/setup/staff?token=synthetic" }; status = 201; }
    else if (path.endsWith("/staff/roles")) data = [
      { id: "role-doctor", name: "doctor", is_system: true, permissions: [] },
      { id: "role-reception", name: "receptionist", is_system: true, permissions: [] },
    ];
    else if (path.endsWith("/staff/permissions")) data = [];
    else if (path.endsWith("/staff/users")) data = [];
    else if (path.endsWith("/staff/invitations")) data = [];
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "test" } }) });
  });

  await page.goto("/manage?tab=access-requests");

  // The pending request is listed; approving grants nothing until the admin acts.
  await expect(page.getByRole("heading", { name: "New Bie" })).toBeVisible();
  await expect(page.getByText("newbie@clinic.test")).toBeVisible();

  await page.getByRole("button", { name: "Approve", exact: true }).click();
  // The approval drawer lets the admin choose the role the person will receive.
  await page.getByLabel("Role").selectOption("doctor");
  await page.getByRole("button", { name: /approve & invite/i }).click();

  // After approval the request leaves the pending queue.
  await expect(page.getByText("No pending requests")).toBeVisible();
  await expect(page.getByText("newbie@clinic.test")).toHaveCount(0);
});

test("public access-request form submits and confirms without granting access", async ({ page }) => {
  let submittedBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/public/access-requests", async (route) => {
    submittedBody = JSON.parse(route.request().postData() ?? "{}");
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ data: { status: "submitted", message: "Your request has been received." }, meta: { request_id: "test" } }) });
  });

  await page.goto("/request-access/synthetic-care");
  await page.getByLabel("Your work email").fill("applicant@clinic.test");
  await page.getByLabel(/Role or department/i).fill("Reception");
  await page.getByRole("button", { name: /request access/i }).click();

  await expect(page.getByText(/your request has been received/i)).toBeVisible();
  // The clinic is taken from the URL slug, never a field the requester picks.
  expect(submittedBody).toMatchObject({ clinic_slug: "synthetic-care", email: "applicant@clinic.test", requested_role: "Reception" });
});
