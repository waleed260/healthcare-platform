"use client";

import { useEffect } from "react";

// Auto-capitalize the first letter of appropriate free-text inputs as the user types.
// Opt-out per element with data-no-capitalize or input[type] in the exclusion list.
// Does not title-case other words. Preserves cursor position.

const EXCLUDED_TYPES = new Set([
  "email", "password", "url", "tel", "search", "number", "date", "datetime-local", "time", "month", "week", "color", "file", "range", "hidden", "checkbox", "radio",
]);

const EXCLUDED_NAMES = /mrn|code|username|license|tax|slug|url|email|password|api|token|npi|cnic|identifier|sku|barcode|reference/i;
const EXCLUDED_AUTOCOMPLETE = /email|username|new-password|current-password|one-time-code/i;
const EXCLUDED_INPUTMODE = /url|email|tel|numeric|decimal/i;

function shouldCapitalize(el: HTMLInputElement | HTMLTextAreaElement): boolean {
  if (el.dataset.noCapitalize != null) return false;
  if (el.getAttribute("autocapitalize") === "off" || el.getAttribute("autocapitalize") === "none") return false;
  const type = (el as HTMLInputElement).type?.toLowerCase();
  if (type && EXCLUDED_TYPES.has(type)) return false;
  const name = el.name || el.id || "";
  if (EXCLUDED_NAMES.test(name)) return false;
  const ac = el.getAttribute("autocomplete") || "";
  if (EXCLUDED_AUTOCOMPLETE.test(ac)) return false;
  const im = el.getAttribute("inputmode") || "";
  if (EXCLUDED_INPUTMODE.test(im)) return false;
  return true;
}

function dispatchReactChange(el: HTMLInputElement | HTMLTextAreaElement, nextValue: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, nextValue);
  else el.value = nextValue;
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

export default function AutoCapitalize() {
  useEffect(() => {
    const handler = (event: Event) => {
      const el = event.target as HTMLElement | null;
      if (!el) return;
      if (!(el instanceof HTMLInputElement) && !(el instanceof HTMLTextAreaElement)) return;
      if (!shouldCapitalize(el)) return;
      const value = el.value;
      if (!value) return;
      const firstChar = value[0];
      if (!/\p{L}/u.test(firstChar)) return;
      const upper = firstChar.toUpperCase();
      if (upper === firstChar) return;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      const nextValue = upper + value.slice(1);
      dispatchReactChange(el, nextValue);
      if (start != null && end != null) {
        try { el.setSelectionRange(start, end); } catch { /* ignore */ }
      }
    };
    document.addEventListener("input", handler, true);
    return () => document.removeEventListener("input", handler, true);
  }, []);
  return null;
}
