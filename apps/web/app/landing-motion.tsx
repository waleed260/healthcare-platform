"use client";

import { useEffect } from "react";

export default function LandingMotion() {
  useEffect(() => {
    let frame = 0;
    let observer: IntersectionObserver | null = null;
    let onScroll: (() => void) | null = null;

    frame = window.requestAnimationFrame(() => {
      const reveals = document.querySelectorAll<HTMLElement>(".landing-page [data-reveal]");
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("is-visible");
            observer?.unobserve(entry.target);
          });
        },
        { threshold: 0.1, rootMargin: "0px 0px -6%" },
      );
      reveals.forEach((node) => observer?.observe(node));

      const nav = document.querySelector<HTMLElement>(".lp-nav");
      const progress = document.querySelector<HTMLElement>(".lp-scroll-progress");

      onScroll = () => {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        if (nav) nav.classList.toggle("nav-scrolled", window.scrollY > 24);
        if (progress) progress.style.transform = `scaleX(${max > 0 ? window.scrollY / max : 0})`;
      };
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    });

    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      if (onScroll) window.removeEventListener("scroll", onScroll);
    };
  }, []);

  return null;
}
