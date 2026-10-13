"use client";

import { useRef, useCallback } from "react";

export function useStaggerReveal<T extends HTMLElement>(_deps: unknown[] = []) {
  return useRef<T>(null);
}

export function useFadeIn<T extends HTMLElement>(_delay = 0) {
  return useRef<T>(null);
}

export function useCountUp(_value: number, _duration = 900) {
  return useRef<HTMLElement>(null);
}

export function useCardReveal<T extends HTMLElement>(_selector: string, _deps: unknown[] = []) {
  return useRef<T>(null);
}

export function useTextReveal<T extends HTMLElement>() {
  return useRef<T>(null);
}

export function useShimmer<T extends HTMLElement>() {
  return useRef<T>(null);
}

export function useBounce<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const bounce = useCallback(() => {}, []);
  return { ref, bounce };
}

export function useSummaryReveal<T extends HTMLElement>(_deps: unknown[] = []) {
  return useRef<T>(null);
}

export function usePageEntrance<T extends HTMLElement>() {
  return useRef<T>(null);
}
