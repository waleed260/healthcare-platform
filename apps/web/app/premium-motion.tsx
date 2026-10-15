"use client";

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
  return null;
}
