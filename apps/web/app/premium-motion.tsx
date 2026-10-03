"use client";

import { useEffect } from "react";
import anime from "animejs";

/**
 * Lightweight, accessible scroll/entrance motion powered by anime.js.
 *
 * Progressive enhancement: the initial hidden state is scoped under the
 * `js-anim` class which this component adds to <html> on mount, so without
 * JavaScript every element renders fully visible. It fully respects
 * `prefers-reduced-motion` (elements are revealed instantly, no animation),
 * and only animates opacity/transform — never layout — to stay cheap.
 *
 * Markup contract:
 *   data-anim              → a single element that fades/rises into view
 *   data-anim="stagger"    → a container whose direct children stagger in
 *   data-anim-delay="120"  → optional extra delay (ms)
 */
export default function PremiumMotion() {
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("js-anim");
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-anim]"));
    if (nodes.length === 0) return;

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const reveal = (el: HTMLElement) => {
      const targets = el.dataset.anim === "stagger" ? Array.from(el.children) : [el];
      const base = Number(el.dataset.animDelay ?? 0);
      el.classList.add("anim-done");
      anime({
        targets,
        opacity: [0, 1],
        translateY: [18, 0],
        delay: anime.stagger(70, { start: base }),
        duration: 620,
        easing: "easeOutCubic",
      });
    };

    if (reduce) { nodes.forEach((el) => el.classList.add("anim-done")); return; }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        reveal(entry.target as HTMLElement);
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6%" });
    nodes.forEach((el) => observer.observe(el));

    // Safety net: anything still hidden after 1.6s (e.g. observer missed) is shown.
    const fallback = window.setTimeout(() => nodes.forEach((el) => { if (!el.classList.contains("anim-done")) { el.classList.add("anim-done"); el.style.opacity = "1"; } }), 1600);

    return () => { observer.disconnect(); window.clearTimeout(fallback); };
  }, []);

  return null;
}
