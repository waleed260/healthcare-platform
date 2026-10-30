"use client";

import { useEffect } from "react";

export default function LandingMotion() {
  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    let frame = 0;
    let observer: IntersectionObserver | null = null;
    let onScroll: (() => void) | null = null;
    const cleanups: (() => void)[] = [];

    frame = window.requestAnimationFrame(() => {
      // --- Set stagger initial state via JS (Turbopack drops late CSS rules) ---
      const allStaggers = document.querySelectorAll<HTMLElement>(".landing-page .lp-stagger");
      const ease = "cubic-bezier(.22,1,.36,1)";
      allStaggers.forEach((el) => {
        el.style.opacity = "0";
        el.style.transform = "translateY(16px)";
        el.style.transition = `opacity .5s ${ease}, transform .5s ${ease}`;
      });

      // --- Staggered reveal with cascade ---
      const reveals = document.querySelectorAll<HTMLElement>(".landing-page [data-reveal]");
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            const el = entry.target as HTMLElement;
            el.classList.add("is-visible");

            const children = el.querySelectorAll<HTMLElement>(".lp-stagger");
            children.forEach((child, i) => {
              child.style.transitionDelay = `${i * 80 + 100}ms`;
              child.style.opacity = "1";
              child.style.transform = "none";
            });

            observer?.unobserve(el);
          });
        },
        { threshold: 0.08, rootMargin: "0px 0px -8%" },
      );
      reveals.forEach((node) => observer?.observe(node));

      // --- Nav scroll + progress bar ---
      const nav = document.querySelector<HTMLElement>(".lp-nav");
      const progress = document.querySelector<HTMLElement>(".lp-scroll-progress");

      // --- Parallax on hero visual ---
      const heroVisual = document.querySelector<HTMLElement>(".lp-hero-visual");

      // --- Counter animation on trust bar ---
      const trustBar = document.querySelector<HTMLElement>(".lp-trust-bar");
      let countersAnimated = false;

      const trustObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting || countersAnimated) return;
            countersAnimated = true;
            animateCounters();
            trustObserver.disconnect();
          });
        },
        { threshold: 0.3 },
      );
      if (trustBar) trustObserver.observe(trustBar);

      // --- Floating animation for preview components ---
      const floaters = document.querySelectorAll<HTMLElement>(
        ".lp-phone, .lp-queue-preview, .lp-followup-preview",
      );
      floaters.forEach((el, i) => {
        el.style.animation = `lp-float ${3 + (i % 3) * 0.4}s ease-in-out infinite`;
        el.style.animationDelay = `${i * 0.5}s`;
      });

      // --- 3D tilt on hover for cards ---
      const tiltCards = document.querySelectorAll<HTMLElement>(
        ".lp-sec-card, .lp-testimonial-card",
      );
      tiltCards.forEach((card) => {
        const handleMouseMove = (e: MouseEvent) => {
          const rect = card.getBoundingClientRect();
          const x = (e.clientX - rect.left) / rect.width - 0.5;
          const y = (e.clientY - rect.top) / rect.height - 0.5;
          card.style.transform = `perspective(600px) rotateY(${x * 6}deg) rotateX(${-y * 6}deg) translateY(-4px)`;
        };
        const handleMouseLeave = () => {
          card.style.transform = "";
        };
        card.addEventListener("mousemove", handleMouseMove);
        card.addEventListener("mouseleave", handleMouseLeave);
        cleanups.push(() => {
          card.removeEventListener("mousemove", handleMouseMove);
          card.removeEventListener("mouseleave", handleMouseLeave);
        });
      });

      // --- Smooth FAQ accordion ---
      const details = document.querySelectorAll<HTMLDetailsElement>(".lp-faq-list details");
      details.forEach((detail) => {
        const summary = detail.querySelector("summary")!;
        const content = detail.querySelector("p")!;
        if (!content) return;

        const handleClick = (e: Event) => {
          e.preventDefault();
          if (detail.open) {
            content.style.maxHeight = content.scrollHeight + "px";
            requestAnimationFrame(() => {
              content.style.maxHeight = "0";
              content.style.opacity = "0";
            });
            setTimeout(() => {
              detail.open = false;
            }, 250);
          } else {
            detail.open = true;
            content.style.maxHeight = "0";
            content.style.opacity = "0";
            requestAnimationFrame(() => {
              content.style.maxHeight = content.scrollHeight + "px";
              content.style.opacity = "1";
            });
            setTimeout(() => {
              content.style.maxHeight = "none";
            }, 300);
          }
        };
        summary.addEventListener("click", handleClick);
        cleanups.push(() => summary.removeEventListener("click", handleClick));
      });

      // --- Scroll handler ---
      let ticking = false;
      onScroll = () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
          const scrollY = window.scrollY;
          const max = document.documentElement.scrollHeight - window.innerHeight;

          if (nav) nav.classList.toggle("nav-scrolled", scrollY > 24);
          if (progress) progress.style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;

          // Parallax
          if (heroVisual && scrollY < 1200) {
            heroVisual.style.transform = `translateY(${scrollY * 0.08}px)`;
          }

          ticking = false;
        });
      };
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    });

    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      if (onScroll) window.removeEventListener("scroll", onScroll);
      cleanups.forEach((fn) => fn());
    };
  }, []);

  return (
    <style>{`
.landing-page .lp-stagger{opacity:0;transform:translateY(16px);transition:opacity .5s cubic-bezier(.22,1,.36,1),transform .5s cubic-bezier(.22,1,.36,1)}
.landing-page .lp-stagger.is-visible{opacity:1;transform:none}
@keyframes lp-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
.lp-sec-card,.lp-testimonial-card{transition:transform .25s cubic-bezier(.22,1,.36,1),box-shadow .25s ease;will-change:transform}
.lp-faq-list details p{overflow:hidden;transition:max-height .25s cubic-bezier(.22,1,.36,1),opacity .2s ease}
.lp-hero-visual{will-change:transform;transition:none}
.lp-showcase-visual>*{transition:opacity .6s cubic-bezier(.22,1,.36,1),transform .6s cubic-bezier(.22,1,.36,1)}
.lp-trust-stat strong{transition:color .3s ease}
.landing-page .lp-step.is-visible .lp-step-number{animation:lp-step-pop .5s cubic-bezier(.22,1,.36,1)}
@keyframes lp-step-pop{0%{transform:scale(0.7);opacity:0}100%{transform:scale(1);opacity:1}}
`}</style>
  );
}

function animateCounters() {
  const stats = document.querySelectorAll<HTMLElement>(".lp-trust-stat strong");
  stats.forEach((el) => {
    const text = el.textContent || "";
    const numMatch = text.match(/[\d.]+/);
    if (!numMatch) return;

    const target = parseFloat(numMatch[0]);
    const prefix = text.slice(0, text.indexOf(numMatch[0]));
    const suffix = text.slice(text.indexOf(numMatch[0]) + numMatch[0].length);
    const isFloat = numMatch[0].includes(".");
    const duration = 1200;
    const start = performance.now();

    const step = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = target * eased;
      el.textContent = prefix + (isFloat ? current.toFixed(1) : Math.round(current).toString()) + suffix;
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
