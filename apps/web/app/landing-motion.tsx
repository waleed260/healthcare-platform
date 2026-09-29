"use client";

import { useEffect } from "react";

export default function LandingMotion() {
  useEffect(() => {
    let frame = 0;
    let observer: IntersectionObserver | null = null;
    let update: (() => void) | null = null;
    frame = window.requestAnimationFrame(() => {
      const revealNodes = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal], .landing-page .product-story, .landing-page .feature-bento, .landing-page .how-section, .landing-page .security-section, .landing-page .template-section, .landing-page .faq-section, .landing-page .final-cta"));
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer?.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -8%" });
      revealNodes.forEach((node) => observer?.observe(node));

      const nav = document.querySelector<HTMLElement>(".landing-page .nav");
      const progress = document.querySelector<HTMLElement>(".scroll-progress");
      update = () => {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        if (nav) nav.classList.toggle("nav-scrolled", window.scrollY > 24);
        if (progress) progress.style.transform = `scaleX(${max > 0 ? window.scrollY / max : 0})`;
      };
      update();
      window.addEventListener("scroll", update, { passive: true });
    });
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      if (update) window.removeEventListener("scroll", update);
    };
  }, []);

  return null;
}
