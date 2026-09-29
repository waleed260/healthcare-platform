# Landing motion system

The landing page uses progressive enhancement. Its static HTML remains readable
before JavaScript runs, and the only animated properties are `transform` and
`opacity`.

## Tokens

- `--motion-fast`: 160ms, `cubic-bezier(.2,.8,.2,1)` for controls and links.
- `--motion-base`: 420ms, `cubic-bezier(.22,1,.36,1)` for reveals.
- `--motion-slow`: 720ms, `cubic-bezier(.16,1,.3,1)` for the hero composition.
- Stagger steps are 70ms and capped at five items.

## Rules

- Hero copy and product composition enter in a short stagger on initial load.
- Sections marked `data-reveal` enter through `IntersectionObserver`; observers
  are disconnected after an element becomes visible.
- The navigation blur/shrink state and scroll progress are driven by passive
  scroll listeners. No layout property is animated.
- Decorative loops are CSS-only and pause when offscreen through the same
  visibility class. There are no offscreen timers.
- `prefers-reduced-motion: reduce` disables transitions, keyframes, scroll
  reveals, and progress movement while preserving the static composition.
- No animation dependency is justified: the implementation uses CSS and the
  Web platform only, so bundle delta is zero.
