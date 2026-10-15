import js from "@eslint/js";
import nextPlugin from "@next/eslint-plugin-next";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import globals from "globals";

export default [
  {
    ignores: [".next/**", "next-env.d.ts", "playwright-report/**", "test-results/**"],
  },
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: {
      "@next/next": nextPlugin,
      "@typescript-eslint": tsPlugin,
    },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      // @typescript-eslint/no-unused-vars is TS-aware (type annotations, `_` prefix):
      // core no-unused-vars false-positives on type params, so it is disabled here.
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      // Auth-expiry redirects (redirectToLogin) are intentional full navigations: a
      // router.push would keep stale in-memory state from the expired session alive.
      "@next/next/no-location-assign-relative-destination": "off",
      // Public clinic-site sections render user-uploaded media from arbitrary clinic
      // domains; next/image would need an unbounded remotePatterns allowlist.
      "@next/next/no-img-element": "off",
    },
  },
];
