import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";

const clinic = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Synthetic Care Clinic",
  slug: "synthetic-care",
  status: "active",
  timezone: "UTC",
  locale: "en-US",
  version: 1,
};

async function installSyntheticApi(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path.endsWith("/clinic") || path.endsWith("/clinic/context")) data = clinic;
    if (path.endsWith("/clinic/onboarding")) {
      data = { completed: false, completed_at: null, steps: {}, ready_to_complete: false };
    }
    if (path.endsWith("/dashboard-summary")) {
      data = { today_appointments: 0, pending_approvals: 0, followups_due: 0 };
    }
    if (path.endsWith("/public/catalog")) {
      data = {
        clinic: { name: clinic.name, timezone: clinic.timezone },
        branches: [{ id: "branch-1", name: "Main clinic", address: null, timezone: "UTC" }],
        services: [{ id: "service-1", name: "General consultation", short_description: null, duration_minutes: 30, branch_id: "branch-1" }],
        doctors: [],
      };
    }
    if (path.endsWith("/public/availability")) data = { slots: [] };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data, meta: { request_id: "00000000-0000-0000-0000-000000000002" } }),
    });
  });
}

const coreRoutes = ["/", "/login", "/onboarding", "/dashboard", "/schedule", "/patients", "/queue", "/operations", "/privacy", "/website", "/admin/governance", "/book/synthetic-care", "/reset-password"];

test.describe("core responsive browser flows", () => {
  test.beforeEach(async ({ page }) => {
    await installSyntheticApi(page);
  });

  for (const route of coreRoutes) {
    test(`renders ${route} with a named main landmark`, async ({ page }) => {
      await page.goto(route);
      await expect(page.locator("main")).toHaveCount(1);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator("h1").first()).toBeVisible();
    });
  }

  test("booking is usable at a mobile breakpoint", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/book/synthetic-care");
    await expect(page.getByRole("heading", { name: /make time for/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /request appointment/i })).toBeDisabled();
  });

  test("keyboard focus is visible on the public entry flow", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
  });

  test("web responses include nonce-based security headers", async ({ page }) => {
    const response = await page.goto("/");
    expect(response).not.toBeNull();
    const headers = response?.headers() ?? {};
    expect(headers["content-security-policy"]).toContain("script-src 'self' 'nonce-");
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
  });

  test("patient directory appends the next cursor page", async ({ page }) => {
    let cursorRequests = 0;
    await page.route("**/api/v1/patients*", async (route) => {
      const hasCursor = Boolean(new URL(route.request().url()).searchParams.get("cursor"));
      if (hasCursor) cursorRequests += 1;
      const patient = hasCursor
        ? { id: "patient-2", patient_number: "SYN-0002", full_name: "Synthetic Second", normalized_email: null, normalized_phone: null, status: "active", version: 1 }
        : { id: "patient-1", patient_number: "SYN-0001", full_name: "Synthetic First", normalized_email: null, normalized_phone: null, status: "active", version: 1 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [patient], meta: { next_cursor: hasCursor ? null : "synthetic-next-cursor" } }) });
    });
    await page.goto("/patients");
    await expect(page.getByText("Synthetic First")).toBeVisible();
    await page.getByRole("button", { name: /load more patient records/i }).click();
    await expect(page.getByText("Synthetic Second")).toBeVisible();
    expect(cursorRequests).toBe(1);
    await expect(page.getByRole("button", { name: /load more patient records/i })).toHaveCount(0);
  });

  test("patient detail renders only the authorized care-team response", async ({ page }) => {
    await page.route("**/api/v1/patients/patient-1**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];
      if (path.endsWith("/care-team")) data = [{ doctor_id: "doctor-1", public_name: "Synthetic Care Doctor", specialty: "General care", created_at: "2026-01-01T09:00:00Z" }];
      else if (path.endsWith("/notes")) data = [{ id: "note-1", note_type: "care", visibility: "care_team", body: "Synthetic scoped note", created_at: "2026-01-01T09:00:00Z" }];
      else if (path.endsWith("/contacts")) data = [];
      else if (path.endsWith("/documents")) data = [{ id: "document-1", original_filename: "synthetic-referral.pdf", mime_type: "application/pdf", size_bytes: 2048, scan_status: "clean", retention_class: "clinical", created_at: "2026-01-01T09:00:00Z", version: 1 }];
      else data = { id: "patient-1", patient_number: "SYN-0001", full_name: "Synthetic First", normalized_email: null, normalized_phone: null, date_of_birth: null, status: "active", version: 1 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "00000000-0000-0000-0000-000000000002" } }) });
    });
    await page.goto("/patients/patient-1");
    await expect(page.getByRole("heading", { name: "Assigned clinicians" })).toBeVisible();
    await expect(page.getByText("Synthetic Care Doctor")).toBeVisible();
    await expect(page.getByText("Synthetic scoped note")).toBeVisible();
  });

  test("patient detail downloads only a clean private document through signed access", async ({ page }) => {
    let accessHeaders: Record<string, string> | null = null;
    await page.route("**/api/v1/patients/patient-1**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = { id: "patient-1", patient_number: "SYN-0001", full_name: "Synthetic First", normalized_email: null, normalized_phone: null, date_of_birth: null, status: "active", version: 1 };
      if (path.endsWith("/documents") || path.endsWith("/contacts") || path.endsWith("/notes") || path.endsWith("/care-team")) data = path.endsWith("/documents") ? [{ id: "document-1", original_filename: "synthetic-referral.pdf", mime_type: "application/pdf", size_bytes: 2048, scan_status: "clean", retention_class: "clinical", created_at: "2026-01-01T09:00:00Z", version: 1 }] : [];
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "00000000-0000-0000-0000-000000000002" } }) });
    });
    await page.route("**/api/v1/documents/document-1/signed-access", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { access_token: "synthetic-document-token", expires_at: 4102444800 } }) });
    });
    await page.route("**/api/v1/documents/document-1/download", async (route) => {
      accessHeaders = route.request().headers();
      await route.fulfill({ status: 200, contentType: "application/pdf", body: "synthetic-pdf" });
    });
    await page.goto("/patients/patient-1");
    await expect(page.getByText("synthetic-referral.pdf")).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download" }).click();
    await download;
    expect(accessHeaders?.["x-document-access-token"]).toBe("synthetic-document-token");
    expect(accessHeaders?.["x-document-expires"]).toBe("4102444800");
  });

  test("queue appends the next cursor page", async ({ page }) => {
    let cursorRequests = 0;
    await page.route("**/api/v1/operations/queue*", async (route) => {
      const hasCursor = Boolean(new URL(route.request().url()).searchParams.get("cursor"));
      if (hasCursor) cursorRequests += 1;
      const entry = hasCursor
        ? { id: "queue-2", appointment_id: "appointment-2", status: "waiting", checked_in_at: "2026-09-16T09:01:00Z", priority: 0, full_name: "Synthetic Second", reference: "SYN-0002", starts_at: "2026-09-16T09:30:00Z", version: 1 }
        : { id: "queue-1", appointment_id: "appointment-1", status: "waiting", checked_in_at: "2026-09-16T09:00:00Z", priority: 0, full_name: "Synthetic First", reference: "SYN-0001", starts_at: "2026-09-16T09:30:00Z", version: 1 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [entry], meta: { next_cursor: hasCursor ? null : "synthetic-queue-cursor" } }) });
    });
    await page.goto("/queue");
    await expect(page.getByText("Synthetic First")).toBeVisible();
    await page.getByRole("button", { name: /load more queue entries/i }).click();
    await expect(page.getByText("Synthetic Second")).toBeVisible();
    expect(cursorRequests).toBe(1);
    await expect(page.getByRole("button", { name: /load more queue entries/i })).toHaveCount(0);
  });

  test("operations completes a scoped follow-up and marks a notification read", async ({ page }) => {
    let completed = false;
    let markedRead = false;
    await page.route("**/api/v1/operations/follow-ups**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ id: "follow-up-1", reason: "Synthetic callback", due_at: "2026-09-22T09:00:00Z", priority: "high", status: "due", version: 1 }], meta: { next_cursor: null } }) });
    });
    await page.route("**/api/v1/operations/notifications**", async (route) => {
      if (route.request().method() === "POST") { markedRead = true; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { marked_read: 1 } }) }); return; }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ id: "notification-1", kind: "follow_up", title: "Synthetic alert", body: "A synthetic task needs attention.", read_at: null, created_at: "2026-09-22T08:00:00Z" }], meta: { next_cursor: null } }) });
    });
    await page.route("**/api/v1/operations/follow-ups/follow-up-1/complete", async (route) => { completed = true; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { id: "follow-up-1", status: "completed", version: 2 } }) }); });
    await page.goto("/operations");
    await expect(page.getByText("Synthetic callback")).toBeVisible();
    await page.getByRole("button", { name: "Complete" }).click();
    await expect.poll(() => completed).toBe(true);
    await page.getByRole("button", { name: /mark read/i }).click();
    await expect.poll(() => markedRead).toBe(true);
  });

  test("operations reports unavailable browser alerts when push is not configured", async ({ page }) => {
    await page.route("**/api/v1/operations/notifications/push-config", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { enabled: false, public_key: null } }) });
    });
    await page.goto("/operations");
    await expect(page.getByRole("heading", { name: "Push notifications" })).toBeVisible();
    await expect(page.getByText("Browser alerts are not configured for this deployment.")).toBeVisible();
    await expect(page.getByRole("button", { name: /enable browser alerts/i })).toHaveCount(0);
  });

  test("operations enables browser alerts through the push subscription flow", async ({ page }) => {
    const vapidKey = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(65)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    let subscribed = false;
    await page.route("**/api/v1/operations/notifications/push-config", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { enabled: true, public_key: vapidKey } }) });
    });
    await page.route("**/api/v1/operations/notifications/push-subscriptions", async (route) => {
      subscribed = true;
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ data: { endpoint: "https://push.example.test/synthetic" } }) });
    });
    await page.addInitScript(() => {
      // Playwright's Chromium runs without a real push service, so stand in a
      // minimal fake of the service-worker registration and push manager.
      const fakeSubscription = {
        endpoint: "https://push.example.test/synthetic",
        toJSON: () => ({ endpoint: "https://push.example.test/synthetic", keys: { p256dh: "synthetic-p256dh", auth: "synthetic-auth" } }),
      };
      Object.defineProperty(navigator, "serviceWorker", {
        value: {
          register: async () => ({ pushManager: { getSubscription: async () => null, subscribe: async () => fakeSubscription } }),
        },
        configurable: true,
      });
      Object.defineProperty(window, "Notification", {
        value: class extends EventTarget {
          static permission = "default";
          static requestPermission = async () => "granted";
        },
        configurable: true,
      });
    });
    await page.goto("/operations");
    await expect(page.getByRole("heading", { name: "Push notifications" })).toBeVisible();
    const enable = page.getByRole("button", { name: /enable browser alerts/i });
    await expect(enable).toBeVisible();
    await enable.click();
    await expect(page.getByText("Alerts are enabled on this device.")).toBeVisible();
    await expect(page.getByText("enabled", { exact: true })).toBeVisible();
    await expect.poll(() => subscribed).toBe(true);
  });

  test("privacy workspace records and approves a synthetic access request", async ({ page }) => {
    let created = false;
    let approved = false;
    await page.route("**/api/v1/governance/privacy-requests**", async (route) => {
      if (route.request().method() === "POST") { approved = true; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { id: "privacy-1", status: "approved" } }) }); return; }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ id: "privacy-1", patient_id: "patient-1", request_type: "access", status: "requested", reason: "Synthetic access review", requested_at: "2026-09-22T08:00:00Z", identity_verified_at: "2026-09-22T08:10:00Z" }], meta: { next_cursor: null } }) });
    });
    await page.route("**/api/v1/governance/patients/patient-1/privacy-requests", async (route) => { created = true; await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ data: { id: "privacy-1", status: "requested" } }) }); });
    await page.goto("/privacy");
    await page.getByLabel("Patient ID").fill("patient-1");
    await page.getByLabel("Reason").fill("Synthetic access review");
    await page.getByRole("button", { name: /record request/i }).click();
    await expect.poll(() => created).toBe(true);
    await page.getByRole("button", { name: "Approve" }).click();
    await expect.poll(() => approved).toBe(true);
  });

  test("onboarding submits the first branch through the protected API", async ({ page }) => {
    let submitted = false;
    page.on("request", (request) => {
      if (request.url().endsWith("/api/v1/branches") && request.method() === "POST") submitted = true;
    });
    await page.goto("/onboarding");
    await page.getByLabel("Branch name").fill("Synthetic Main Clinic");
    await page.getByRole("button", { name: /save branch/i }).click();
    await expect.poll(() => submitted).toBe(true);
  });

  test("public booking submits a synthetic appointment request", async ({ page }) => {
    const bookingDay = new Date();
    bookingDay.setDate(bookingDay.getDate() + 7);
    const day = bookingDay.toISOString().slice(0, 10);
    await page.route("**/api/v1/public/availability**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { slots: [`${day}T09:00:00Z`] } }) });
    });
    await page.route("**/api/v1/public/bookings", async (route) => {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ data: { reference: "SYN-0001", status: "pending", management_secret: "synthetic-secret" } }) });
    });
    await page.goto("/book/synthetic-care");
    await page.getByLabel("Date").fill(day);
    await expect(page.locator(".slot")).toHaveCount(1);
    await page.locator(".slot").click();
    await page.getByLabel("Full name").fill("Synthetic Booking");
    await page.getByRole("button", { name: /request appointment/i }).click();
    await expect(page.getByRole("heading", { name: /you.re on the list/i })).toBeVisible();
    await expect(page.getByText("SYN-0001")).toBeVisible();
  });

  test("manual reset consumes the one-time token and confirms completion", async ({ page }) => {
    let submittedBody: { token?: string; new_password?: string } | null = null;
    await page.route("**/api/v1/auth/manual-reset/consume", async (route) => {
      submittedBody = JSON.parse(route.request().postData() ?? "{}");
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { reset: true } }) });
    });
    await page.goto("/reset-password?token=synthetic-one-time-token");
    await page.getByLabel("New password").fill("SyntheticPassword123");
    await page.getByLabel("Confirm password").fill("SyntheticPassword123");
    await page.getByRole("button", { name: /update password/i }).click();
    await expect(page.getByRole("heading", { name: /you.re ready/i })).toBeVisible();
    expect(submittedBody).toEqual({ token: "synthetic-one-time-token", new_password: "SyntheticPassword123" });
  });

  test("first owner login can enroll MFA before entering the workspace", async ({ page }) => {
    await page.route("**/api/v1/auth/login", async (route) => {
      await route.fulfill({
        status: 200,
        headers: { "set-cookie": "csrf_token=synthetic-csrf; Path=/" },
        contentType: "application/json",
        body: JSON.stringify({ data: { mfa_required: true, mfa_enrollment_required: true } }),
      });
    });
    await page.route("**/api/v1/auth/mfa/enroll", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ secret: "SYNTHETIC-TOTP-SECRET", recovery_codes: ["SYNTHETIC-RECOVERY-1"] }) });
    });
    await page.route("**/api/v1/auth/mfa/verify", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { verified: true } }) });
    });
    await page.goto("/login");
    await page.getByLabel("Clinic email").fill("owner@example.test");
    await page.getByLabel("Password").fill("SyntheticPassword123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText("SYNTHETIC-TOTP-SECRET")).toBeVisible();
    await expect(page.getByText("SYNTHETIC-RECOVERY-1")).toBeVisible();
    await page.getByLabel("First authenticator code").fill("123456");
    await page.getByRole("button", { name: /verify and continue/i }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test("website editor saves a draft section and publishes the version", async ({ page }) => {
    const website = { id: "site-1", name: "Synthetic Clinic Website", template_key: "calm_clinic", status: "draft", version: 1, draft_version_id: "version-1", live_version_id: null };
    const pageRecord = { id: "page-1", slug: "home", title: "Home", seo_title: null, seo_description: null, version: 1 };
    const section = { id: "section-1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Welcome", body: "Synthetic clinic copy." }, is_visible: true, version: 1 };
    await page.route("**/api/v1/websites", async (route) => {
      if (route.request().method() === "GET") await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [website] }) });
      else await route.fallback();
    });
    await page.route("**/api/v1/websites/site-1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/pages") && route.request().method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [pageRecord] }) });
      if (path.endsWith("/versions") && route.request().method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ id: "version-1", version_number: 1, published_at: null, created_at: "2026-01-01T00:00:00Z" }] }) });
      if (path.endsWith("/sections") && route.request().method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [section] }) });
      if (path.endsWith("/section-1") && route.request().method() === "PATCH") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { ...section, content: { ...section.content, heading: "Updated welcome" }, version: 2 } }) });
      if (path.endsWith("/publish") && route.request().method() === "POST") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { ...website, status: "published", version: 2, live_version_id: "version-2" } }) });
      return route.fallback();
    });
    await page.goto("/website");
    await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
    await page.getByLabel("Heading").fill("Updated welcome");
    await page.getByRole("button", { name: /save section/i }).click();
    await expect(page.getByRole("status")).toContainText(/draft saved/i);
    await page.getByRole("button", { name: /publish draft/i }).click();
    await expect(page.getByRole("status")).toContainText(/published/i);
  });

  test("platform governance requires separate retention approval before assignment", async ({ page }) => {
    let created = false;
    let approved = false;
    let assigned = false;
    await page.route("**/api/v1/admin/retention-policies", async (route) => {
      if (route.request().method() === "POST") {
        created = true;
        await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ data: { id: "policy-2", name: "Synthetic policy", jurisdiction: "Synthetic jurisdiction", rules: {}, active: false, approved_by: null, approved_at: null, created_at: "2026-01-01T00:00:00Z" } }) });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: [
              { id: "policy-1", name: "Approved synthetic policy", jurisdiction: "Synthetic jurisdiction", rules: {}, active: true, approved_by: "platform-user", approved_at: "2026-01-01T00:00:00Z", created_at: "2026-01-01T00:00:00Z" },
              { id: "policy-draft", name: "Draft synthetic policy", jurisdiction: "Review jurisdiction", rules: {}, active: false, approved_by: null, approved_at: null, created_at: "2026-01-02T00:00:00Z" },
            ],
          }),
        });
      }
    });
    await page.route("**/api/v1/admin/retention-policies/policy-draft/approve", async (route) => { approved = true; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { id: "policy-draft", active: true } }) }); });
    await page.route("**/api/v1/admin/clinics", async (route) => { await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ id: "clinic-1", name: "Synthetic Care Clinic", slug: "synthetic-care", status: "active" }] }) }); });
    await page.route("**/api/v1/admin/clinics/clinic-1/retention-policy", async (route) => { assigned = true; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { clinic_id: "clinic-1", retention_policy_id: "policy-1" } }) }); });
    await page.goto("/admin/governance");
    await expect(page.getByRole("heading", { name: "Retention policies" })).toBeVisible();
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByRole("status")).toContainText(/approved/i);
    await page.getByLabel("Policy name").fill("Synthetic new policy");
    await page.locator("#policy-jurisdiction").fill("New synthetic jurisdiction");
    await page.getByRole("button", { name: /create inactive policy/i }).click();
    await expect.poll(() => created).toBe(true);
    await page.getByRole("button", { name: /assign policy/i }).click();
    await expect.poll(() => assigned).toBe(true);
    expect(approved).toBe(true);
  });

  for (const route of coreRoutes) {
    test(`${route} has no automated WCAG violations`, async ({ page }) => {
      await page.goto(route);
      if (route.startsWith("/book/")) {
        await expect(page.getByRole("heading", { name: /make time for|you.re on the list/i })).toBeVisible();
      } else {
        await expect(page.locator("h1").first()).toBeVisible();
      }
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });
  }
});
