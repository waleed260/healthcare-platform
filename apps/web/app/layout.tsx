import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Carefully run clinics | Healthcare Platform",
  description: "A calm operating system for independent clinics and their patients.",
};

// The nonce-based CSP is generated per request; static HTML cannot carry it safely.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
