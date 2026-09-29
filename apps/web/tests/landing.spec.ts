import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

test.describe("landing experience", () => {
  for (const width of [375, 768, 1440]) {
    test(`is readable at ${width}px without JavaScript motion`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/");
      await expect(page.getByRole("heading", { name: /make care feel/i })).toBeVisible();
      await expect(page.getByRole("heading", { name: /the front door/i })).toBeVisible();
      await expect(page.getByRole("heading", { name: /trust is part/i })).toBeVisible();
      expect(errors).toEqual([]);
    });
  }

  test("has no axe contrast violations in the primary viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
    expect(results.violations).toEqual([]);
  });
});
