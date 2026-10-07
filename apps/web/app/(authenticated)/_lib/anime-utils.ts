"use client";

import { useEffect, useRef, useCallback } from "react";
import anime from "animejs";

/** Fade-in + slide-up for a container's direct children, staggered */
export function useStaggerReveal<T extends HTMLElement>(deps: unknown[] = []) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const children = el.querySelectorAll(":scope > *");
    if (!children.length) return;
    anime({
      targets: Array.from(children),
      opacity: [0, 1],
      translateY: [18, 0],
      duration: 520,
      delay: anime.stagger(60, { start: 80 }),
      easing: "easeOutCubic",
    });
  }, deps);
  return ref;
}

/** Animate a single element on mount: fade-in + slight rise */
export function useFadeIn<T extends HTMLElement>(delay = 0) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    anime({
      targets: el,
      opacity: [0, 1],
      translateY: [14, 0],
      duration: 500,
      delay,
      easing: "easeOutCubic",
    });
  }, []);
  return ref;
}

/** Count-up animation for a number display */
export function useCountUp(value: number, duration = 900) {
  const ref = useRef<HTMLElement>(null);
  const prevValue = useRef(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || value === prevValue.current) return;
    const obj = { val: prevValue.current };
    anime({
      targets: obj,
      val: value,
      round: 1,
      duration,
      easing: "easeOutExpo",
      update: () => { el.textContent = String(obj.val); },
    });
    prevValue.current = value;
  }, [value, duration]);
  return ref;
}

/** Stagger-reveal for card grids (invoice-list rows, summary cards) */
export function useCardReveal<T extends HTMLElement>(selector: string, deps: unknown[] = []) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const cards = el.querySelectorAll(selector);
    if (!cards.length) return;
    anime({
      targets: Array.from(cards),
      opacity: [0, 1],
      translateY: [22, 0],
      scale: [0.97, 1],
      duration: 480,
      delay: anime.stagger(45, { start: 100 }),
      easing: "easeOutCubic",
    });
  }, deps);
  return ref;
}

/** Hero heading letter-by-letter reveal */
export function useTextReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const text = el.textContent ?? "";
    el.innerHTML = text.split("").map((ch) =>
      ch === " " ? " " : `<span class="anim-letter" style="display:inline-block;opacity:0">${ch}</span>`
    ).join("");
    anime({
      targets: el.querySelectorAll(".anim-letter"),
      opacity: [0, 1],
      translateY: [20, 0],
      rotateZ: [-4, 0],
      duration: 600,
      delay: anime.stagger(25, { start: 200 }),
      easing: "easeOutCubic",
    });
  }, []);
  return ref;
}

/** Shimmer pulse for loading skeletons */
export function useShimmer<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    anime({
      targets: el,
      opacity: [0.45, 1],
      duration: 1200,
      direction: "alternate",
      loop: true,
      easing: "easeInOutSine",
    });
  }, []);
  return ref;
}

/** Micro-interaction: scale bounce on click */
export function useBounce<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const bounce = useCallback(() => {
    if (!ref.current) return;
    anime({
      targets: ref.current,
      scale: [1, 0.94, 1.03, 1],
      duration: 350,
      easing: "easeOutCubic",
    });
  }, []);
  return { ref, bounce };
}

/** Animate summary stat cards (the inventory-summary / hero stats) */
export function useSummaryReveal<T extends HTMLElement>(deps: unknown[] = []) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const cards = el.querySelectorAll(":scope > div");
    if (!cards.length) return;
    anime({
      targets: Array.from(cards),
      opacity: [0, 1],
      translateY: [28, 0],
      scale: [0.92, 1],
      duration: 600,
      delay: anime.stagger(90, { start: 120 }),
      easing: "easeOutExpo",
    });
  }, deps);
  return ref;
}

/** Page-level entrance: animate the workspace-page-header + body */
export function usePageEntrance<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const header = el.querySelector(".workspace-page-header");
    const sections = el.querySelectorAll(".surface-card, .inventory-summary, .pipeline-toolbar");
    if (header) {
      anime({
        targets: header,
        opacity: [0, 1],
        translateY: [-12, 0],
        duration: 500,
        easing: "easeOutCubic",
      });
    }
    if (sections.length) {
      anime({
        targets: Array.from(sections),
        opacity: [0, 1],
        translateY: [30, 0],
        duration: 550,
        delay: anime.stagger(80, { start: 250 }),
        easing: "easeOutCubic",
      });
    }
  }, []);
  return ref;
}
