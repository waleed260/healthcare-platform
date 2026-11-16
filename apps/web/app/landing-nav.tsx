"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const links = [["#product", "Product"], ["#how-it-works", "How it works"], ["#security", "Security"], ["#pricing", "Pricing"]];

export default function LandingNav() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <nav className={`lp-nav shell${open ? " is-open" : ""}`} aria-label="Primary navigation">
      <Link className="wordmark" href="/">care<span>/</span>fully</Link>
      <button type="button" className="lp-hamburger" aria-expanded={open} aria-controls="lp-nav-links" aria-label={open ? "Close navigation menu" : "Open navigation menu"} onClick={() => setOpen((value) => !value)}>
        <span /><span /><span />
      </button>
      <div className="lp-nav-links" id="lp-nav-links" onClick={() => setOpen(false)}>
        {links.map(([href, label]) => <a key={href} href={href}>{label}</a>)}
        <Link className="lp-nav-signin" href="/login">Sign in</Link>
        <Link className="lp-nav-cta" href="#pricing">Request a demo <span>→</span></Link>
      </div>
    </nav>
  );
}
