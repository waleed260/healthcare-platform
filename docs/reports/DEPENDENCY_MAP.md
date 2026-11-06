# Dependency Map — Workflow Repair

## Clinical Workflow Chain

```
Inventory → Services → Appointments → Queue → Encounters → Billing → Finance
```

## Issue-to-Module Map

| Issue | Frontend Files | Backend Files | DB Tables |
|-------|---------------|---------------|-----------|
| 1 | branches/page.tsx | — | — |
| 2 | _lib/add-appointment-drawer.tsx | catalog/routes.py | branch_services, doctor_services |
| 3 | — | appointments/routes.py | appointments, leave_blocks, blocked_slots |
| 4+5 | queue/page.tsx, encounters/page.tsx | operations/routes.py | queue_entries, appointments |
| 6 | _lib/add-appointment-drawer.tsx | appointments/routes.py | appointments (token_number) |
| 7 | — | encounters/routes.py | encounter_forms, inventory_stock, inventory_adjustments |
| 8 | — | inventory/purchase_routes.py | inventory_stock, purchase_orders |

## Cross-Issue Dependencies

- Issue 2 depends on Issue 1 clarity (users need to understand branch vs doctor service assignment)
- Issue 5 depends on Issue 4 context (patient pre-population eliminates the "unbooked patients" concern)
- Issue 7 depends on Issue 8 (stock must be correctly tracked before deduction makes sense)
