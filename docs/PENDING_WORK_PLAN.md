# Pending Work Plan — CRM Spec Gap Closure

> Generated: October 10, 2026
> Based on gap analysis of `/home/waleed/Music/crm .docx` vs current codebase

---

## Phase A — Patient Detail Page Completion (Patient Tabs + Timeline)
**Why first:** Patient detail is the CRM's core screen. Only 3 of 10 tabs work.

1. Add Appointments tab — list patient's appointments with status/doctor/date
2. Add Treatments tab — show treatment plans linked to patient
3. Add Prescriptions tab — list prescriptions with medication details
4. Add Invoices/Payments tab — show invoices, payments, balance
5. Add Documents tab — consent records, uploaded files
6. Add Packages tab — purchased packages, sessions used/remaining
7. Add unified Timeline tab — chronological merge of all events (appointments, notes, vitals, treatments, transfers, payments)
8. Add patient fields: emergency contact, preferred communication, contraindications

## Phase B — Lead Enhancements
**Why:** Leads module missing critical fields for tracking sources and follow-ups.

1. Add lead source fields (Meta Ads, Google Ads, Instagram, Referral, Walk-in, Call, Import)
2. Add campaign/ad metadata, requested service/specialty/branch fields
3. Add owner assignment to leads
4. Add Lost stage with reason + controlled reopening
5. Enhance follow-up with due date + assignee (not just text)

## Phase C — Invoice/Billing Improvements
**Why:** Invoice creation missing service line items linkage, branch assignment.

1. Invoice creation from appointment/treatment/package source linkage
2. Add branch assignment to invoices
3. Outstanding aging report in Finance
4. Inventory low-stock alerts

## Phase D — Doctor Management Enhancements
**Why:** Doctor profiles need extended fields per spec sections 23, 310-311.

1. Extended doctor profile — registration/license, room, appointment duration defaults, working hours, booking status
2. Doctor-specialty-service-branch compatibility validation in booking
3. Doctor template assignments for clinical forms
4. Deactivation preserves history, flags future bookings

## Phase E — Encounter Forms System
**Why:** Spec sections 24-25 — printable encounter/discharge forms are core clinical requirement.

1. Create encounter form data model (FormTemplate, EncounterForm, Observation, MedicationAdministration)
2. Migration for encounter_forms, observations, medication_administrations tables
3. Backend endpoints: create/save/finalize/list encounter forms
4. Encounter form header: clinic info, patient MRN, doctor, arrival observations
5. Assessment sections: complaint, examination, diagnosis, investigations
6. Medicine administration rows
7. Discharge observations + discharge prescriptions
8. Specialty templates (general, emergency, dental, hair, skin)
9. Form lifecycle: draft → review → finalize → print/PDF
10. Printable A4 layout with proper page breaks

## Phase F — Admission & Transfer Workflow
**Why:** Spec sections 26-27 — patient admission and clinical handover.

1. Admission episode model + migration
2. Admit patient action from encounter
3. Admission form: ward/bed, admitting doctor, consultant, expected stay
4. Enhanced transfer with clinical handover data (observations, medications, history)
5. Transfer acceptance workflow (draft → sent → accepted → completed)
6. Bed allocation/release (if configured)

## Phase G — Internal Tasks System
**Why:** Spec section 15 — no task management exists currently.

1. Tasks table: title, type, assignee, due date/time, priority, patient/lead link, status, notes
2. Migration + RLS
3. Backend CRUD endpoints
4. Tasks UI — list with filters, create form, status updates
5. Add tasks to navigation

## Phase H — Website Theme System
**Why:** Spec sections 4-11 — the biggest feature gap. Currently only color presets.

1. Themes landing page — live theme card, draft library
2. Theme instance management — duplicate, rename, archive
3. Draft/live separation — editing creates pending draft
4. Global theme token model (colors, typography, buttons, layout)
5. Enhanced section/block editor controls
6. Responsive preview (desktop/tablet/mobile viewport switching)
7. Undo/redo in editor
8. Version history with actor/timestamp/restore

## Phase I — Website Content & Blog
**Why:** Blog, testimonials, forms not implemented.

1. Blog system — posts CRUD, categories, rich text, SEO
2. Blog UI — index page, article template
3. Testimonials — consent-approved, moderation workflow
4. Website forms — configurable fields, routing, spam protection
5. Dynamic CRM bindings — services/providers/branches on website

## Phase J — Remaining Polish
**Why:** Various smaller gaps from the spec.

1. Age categories — clinic-defined with category-specific fields
2. Expected visit duration — configurable 90min default
3. Arrival/departure/elapsed tracking with overdue timer
4. Custom code editor for themes
5. SEO Open Graph, favicon, slug collision validation
6. Domain lifecycle — primary domain, redirects, canonical URLs

---

## Execution Order
A → B → C → D → E → F → G → H → I → J

Phase A is biggest bang-for-buck — completes the patient detail page which is used constantly.
