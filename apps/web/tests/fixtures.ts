import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { test as base, expect } from "@playwright/test";

/**
 * Browser specs are mocked by default. When PLAYWRIGHT_RESEED=1 is supplied,
 * each test gets a fresh deterministic database seed before its route setup.
 * This keeps real-browser runs independent without inventing a reset API.
 */
function reseedIfRequested() {
  if (process.env.PLAYWRIGHT_RESEED !== "1") return;
  if (!process.env.SEED_DATABASE_URL) {
    throw new Error("PLAYWRIGHT_RESEED=1 requires SEED_DATABASE_URL");
  }

  const repositoryRoot = resolve(process.cwd(), "../..");
  const apiRoot = resolve(repositoryRoot, "apps/api");
  const seedScript = resolve(apiRoot, "scripts/seed_demo.py");
  const python = process.env.SEED_PYTHON_BIN ?? "python3";
  execFileSync(python, [seedScript], {
    cwd: apiRoot,
    stdio: "inherit",
    env: { ...process.env, APP_ENV: "test" },
  });
}

export const test = base.extend<{ reseeded: void }>({
  reseeded: [async ({ page }, use) => {
    void page;
    reseedIfRequested();
    await use();
  }, { auto: true }],
});

export { expect };
