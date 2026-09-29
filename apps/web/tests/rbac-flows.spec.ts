import { test, expect } from "./fixtures";

const roles = [
  { name: "owner", permissions: ["queue.read", "queue.manage", "website.read", "website.edit", "website.publish"] },
  { name: "manager", permissions: ["queue.read", "queue.manage", "website.read", "website.edit", "website.publish"] },
  { name: "doctor", permissions: ["queue.read", "queue.manage", "website.read"] },
  { name: "receptionist", permissions: ["queue.read", "queue.manage", "website.read"] },
  { name: "website editor", permissions: ["website.read", "website.edit"] },
] as const;

for (const role of roles) {
  test(`${role.name} sees allowed controls and blocked controls`, async ({ page }) => {
    let queueCommand = false;
    let sectionSaved = false;
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      let data: unknown = [];
      if (path.endsWith("/auth/me")) data = { clinic_id: "clinic-synthetic", permissions: role.permissions };
      else if (path.endsWith("/operations/queue")) data = [{ id: "queue-1", appointment_id: "appointment-1", status: "waiting", checked_in_at: "2026-09-27T09:00:00Z", priority: 0, full_name: "Synthetic Patient", reference: "SYN-0001", starts_at: "2026-09-27T09:30:00Z", version: 1 }];
      else if (path.endsWith("/start")) { queueCommand = true; data = { id: "queue-1", status: "in_consultation", version: 2 }; }
      else if (path.endsWith("/websites")) data = [{ id: "site-1", name: "Synthetic website", template_key: "calm_clinic", status: "draft", version: 1, draft_version_id: "version-1", live_version_id: null, brand: {} }];
      else if (path.endsWith("/domains")) data = [];
      else if (path.endsWith("/pages")) data = [{ id: "page-1", slug: "home", title: "Home", version: 1 }];
      else if (path.endsWith("/versions")) data = [];
      else if (path.endsWith("/sections")) data = [{ id: "section-1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Synthetic heading", body: "Synthetic body" }, is_visible: true, version: 1 }];
      else if (path.endsWith("/validation")) data = { valid: true, code: null, message: null };
      else if (path.endsWith("/section-1") && request.method() === "PATCH") { sectionSaved = true; data = { id: "section-1", section_type: "hero", layout_key: "split", position: 0, content: { heading: "Updated synthetic heading", body: "Synthetic body" }, is_visible: true, version: 2 }; }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { next_cursor: null } }) });
    });

    await page.goto("/queue");
    const queueAction = page.getByRole("button", { name: /start consultation/i });
    if (role.name === "website editor") {
      await expect(queueAction).toBeDisabled();
    } else {
      await expect(queueAction).toBeEnabled();
      await queueAction.click();
      await expect.poll(() => queueCommand).toBe(true);
    }

    await page.goto("/website");
    const publish = page.getByRole("button", { name: /publish draft/i });
    if (role.name === "owner" || role.name === "manager") await expect(publish).toBeEnabled();
    else await expect(publish).toBeDisabled();
    if (role.name === "website editor") {
      const heading = page.getByLabel("Heading");
      await expect(heading).toBeEnabled();
      await heading.fill("Updated synthetic heading");
      await page.getByRole("button", { name: /save section/i }).click();
      await expect.poll(() => sectionSaved).toBe(true);
    }
  });
}
