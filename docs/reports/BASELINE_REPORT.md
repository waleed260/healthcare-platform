# Baseline Report — Clinic CRM Workflow Repair

**Date**: 2026-11-06

## Issues Reported

| # | Summary | Area | Severity |
|---|---------|------|----------|
| 1 | Duplicate "SERVICES" sections in branch detail | Frontend — branches/page.tsx | UX |
| 2 | Services not appearing in Book Appointment drawer | Frontend — add-appointment-drawer.tsx | Functional |
| 3 | "The selected time is no longer available" — generic rejection | Backend — appointments/routes.py | UX |
| 4 | Encounter patient list shows all patients, not just booked | Frontend — encounters/page.tsx | UX (by design) |
| 5 | Doctor and encounter type not inherited from booking | Frontend — queue/page.tsx → encounters | Functional |
| 6 | No token printed after booking | Full-stack | Feature |
| 7 | Inventory not deducted on encounter treatments | Backend — encounters/routes.py | Functional |
| 8 | Purchased stock not appearing in inventory | Backend — purchase_routes.py | Functional |

## Pre-existing State

- Issues 5 and 6 were **already fixed** in the codebase prior to this session (queue page passes params; token_number generation + print UI exist).
- Issue 4 is by design — encounter patient search is global, not appointment-filtered.
- Issues 1, 2, 3, 7, 8 required code changes.
