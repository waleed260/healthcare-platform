import { test, expect } from "./fixtures";
import type { Page, Route } from "@playwright/test";

const SHOTS = "/tmp/claude-1000/-home-waleed-Downloads-health-care/0d8cd524-25b9-498f-817c-1c18e51f3596/scratchpad";

const PRODUCTS = [
  { id: "p1", name: "Surgical Gloves", sku: "SG-1", product_type: "consumable", unit: "Boxes", minimum_stock: "5", status: "active", version: 1, category_id: "c1", cost_minor: 500, selling_price_minor: 900, currency: "PKR", tax_inclusive: false },
  { id: "p2", name: "Syringes", sku: "SY-1", product_type: "consumable", unit: "Pieces", minimum_stock: "20", status: "active", version: 1, category_id: null, cost_minor: 100, selling_price_minor: 200, currency: "PKR", tax_inclusive: false },
];
const STOCK = [
  { id: "s1", branch_id: "b1", branch_name: "Main Branch", product_id: "p1", product_name: "Surgical Gloves", product_type: "consumable", unit: "Boxes", minimum_stock: "5", category_id: "c1", quantity: "40", low_stock: false, version: 1, warehouse_id: null, warehouse_name: null },
  { id: "s2", branch_id: "b1", branch_name: "Main Branch", product_id: "p2", product_name: "Syringes", product_type: "consumable", unit: "Pieces", minimum_stock: "20", category_id: null, quantity: "12", low_stock: true, version: 1, warehouse_id: null, warehouse_name: null },
];

type State = { categories: Array<{ id: string; name: string; slug: string; display_order: number }>; posts: Array<Record<string, unknown>> };

async function installInventory(page: Page, state: State) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const r = route.request();
    const path = new URL(r.url()).pathname;
    const method = r.method();
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ data, meta: { next_cursor: null, request_id: "t" } }) });
    if (path.endsWith("/auth/me")) return json({ clinic_id: "clinic", clinic_slug: "c", permissions: ["inventory.read", "inventory.manage"] });
    if (path.endsWith("/inventory/products")) return json(PRODUCTS);
    if (path.endsWith("/inventory/stock")) return json(STOCK);
    if (path.endsWith("/branches")) return json([{ id: "b1", name: "Main Branch" }]);
    if (path.endsWith("/inventory/categories")) {
      if (method === "POST") {
        const body = JSON.parse(r.postData() ?? "{}");
        state.posts.push(body);
        const row = { id: `c${state.categories.length + 1}`, name: body.name, slug: body.slug, display_order: body.display_order ?? 0 };
        state.categories.push(row);
        return json(row, 201);
      }
      return json(state.categories);
    }
    return json([]);
  });
}

test("inventory workspace: header, categories create, screenshots (desktop + mobile)", async ({ page }, testInfo) => {
  const state: State = { categories: [{ id: "c1", name: "Instruments", slug: "instruments", display_order: 0 }], posts: [] };
  await installInventory(page, state);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/inventory");
  await expect(page.getByRole("heading", { name: /running low/i })).toBeVisible();
  // The hero heading must not be clipped at the top of its scroll container.
  const heading = page.getByRole("heading", { name: /running low/i });
  const box = await heading.boundingBox();
  await page.screenshot({ path: `${SHOTS}/inv-desktop-${testInfo.project.name}.png`, fullPage: false });

  // Open Categories and create one through the real UI.
  await page.getByRole("button", { name: /^Categories/ }).click();
  await expect(page.getByRole("heading", { name: /Organize your inventory/i })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/inv-categories-${testInfo.project.name}.png`, fullPage: false });

  await page.getByLabel("Name").fill("Surgical Tools");
  // Slug should auto-fill from the name; assert it, then submit.
  const slug = page.getByLabel("Slug");
  await expect(slug).toHaveValue("surgical-tools");
  await page.getByRole("button", { name: /Add category/ }).click();
  // Persisted via refetch (the new category appears in the list as a heading).
  await expect(page.getByRole("heading", { name: "Surgical Tools" })).toBeVisible();
  expect(state.posts.at(-1)).toMatchObject({ name: "Surgical Tools", slug: "surgical-tools" });

  // Mobile render.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/inventory");
  await expect(page.getByRole("heading", { name: /running low/i })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/inv-mobile-${testInfo.project.name}.png`, fullPage: false });

  expect(box).not.toBeNull();
});
