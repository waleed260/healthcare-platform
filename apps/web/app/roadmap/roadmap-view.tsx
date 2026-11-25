"use client";

import { useState } from "react";
import styles from "./roadmap.module.css";

type Node = { title: string; text: string; href: string };
type Lane = { number: string; title: string; subtitle: string; nodes: Node[] };

const lanes: Lane[] = [
  {
    number: "01", title: "Patient journey", subtitle: "Enquiry to completed visit",
    nodes: [
      { title: "Overview", text: "Daily appointments, queue activity, follow-ups and clinic alerts in one operating snapshot.", href: "/dashboard" },
      { title: "Leads", text: "Capture enquiries, track source and stages, keep the activity history and plan the next follow-up.", href: "/leads" },
      { title: "Schedule", text: "Book appointments using clinic availability, doctors, services and branches. Lead bookings retain their lead link and booking token.", href: "/schedule" },
      { title: "Patients", text: "The central patient record: identity, contacts, notes, consent, care team and patient history.", href: "/patients" },
      { title: "Queue", text: "Check patients in when they arrive, manage queue order and move visits into consultation.", href: "/queue" },
      { title: "Follow-ups", text: "Assign and track due work for patients and leads, with completion status.", href: "/operations" }
    ]
  },
  {
    number: "02", title: "Clinical care", subtitle: "People, services and care records",
    nodes: [
      { title: "Branches", text: "Clinic locations, opening hours, rooms and resources. Branch scope shapes operational availability and access.", href: "/branches" },
      { title: "Doctors", text: "Doctor profiles and their branch, service and availability relationships.", href: "/doctors" },
      { title: "Services", text: "The clinic service catalogue used by booking, doctor compatibility and service materials.", href: "/services" },
      { title: "Encounters", text: "The clinical visit record linked to the patient and appointment, including status, prescriptions and discharge.", href: "/encounters" },
      { title: "Clinical", text: "Treatment plans, prescriptions, structured forms and specialty-specific clinical tools.", href: "/clinical" }
    ]
  },
  {
    number: "03", title: "Business operations", subtitle: "Money, stock and reporting",
    nodes: [
      { title: "Billing", text: "Invoices, line items, payments, voids, refunds and receipts.", href: "/billing" },
      { title: "Finance", text: "Clinic expenses, provider revenue, cashier summaries and commission rules.", href: "/finance" },
      { title: "Packages", text: "Service bundles, patient package purchases and session consumption.", href: "/packages" },
      { title: "Inventory", text: "Products, categories, stock adjustments, suppliers, purchases, warehouses and transfers.", href: "/inventory" },
      { title: "Reports", text: "Saved reports and operational analytics, including lead funnel, channels and service summaries.", href: "/reports" }
    ]
  },
  {
    number: "04", title: "Website & acquisition", subtitle: "The public clinic experience",
    nodes: [
      { title: "Website", text: "Clinic pages, sections, themes, preview, publishing and version history.", href: "/website" },
      { title: "Content", text: "Website forms, posts, blog content and testimonials. Public enquiries can enter the Leads pipeline.", href: "/content" },
      { title: "Domains", text: "Connect and verify the clinic's public website hostname.", href: "/domains" },
      { title: "Media", text: "Manage website media and supported private document workflows.", href: "/media" }
    ]
  },
  {
    number: "05", title: "Management & trust", subtitle: "Controls shared across the platform",
    nodes: [
      { title: "Manage", text: "Staff, invitations, roles, permissions, branches, specialties and clinic configuration.", href: "/manage" },
      { title: "Security", text: "Authentication, sessions, MFA and permission-aware access controls.", href: "/security" },
      { title: "Alerts", text: "In-app notifications and supported web-push subscription management.", href: "/notifications" },
      { title: "Privacy", text: "Privacy and governance workflows for controlled handling of clinic information.", href: "/privacy" },
      { title: "Platform", text: "Platform-level governance and access-request administration for platform administrators.", href: "/admin" }
    ]
  }
];

const flow = [
  ["Website / staff enquiry", "Leads", "An enquiry is captured and qualified."],
  ["Leads", "Schedule", "Staff book an appointment linked to the lead."],
  ["Schedule", "Patients + Queue", "Patient association and arrival/check-in."],
  ["Queue", "Encounters", "The visit moves into the clinical record."],
  ["Encounters", "Billing + Follow-ups", "Supported billing hand-off and next actions."],
  ["Services", "Inventory", "Service materials can reference stock products."]
];

export default function RoadmapView() {
  const first = lanes[0].nodes[1];
  const [selected, setSelected] = useState<Node>(first);
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/">care<span>/</span>fully</a>
        <span className={styles.public}><i /> PUBLIC WORKFLOW MAP · READ ONLY</span>
      </header>

      <section className={styles.intro}>
        <p className={styles.eyebrow}>THE CLINIC OPERATING SYSTEM</p>
        <h1>One clinic.<br /><em>One connected workflow.</em></h1>
        <p>A visual roadmap of how the care/fully CRM connects enquiries, appointments, patient records, clinical care, billing, inventory and clinic management.</p>
      </section>

      <section className={styles.map}>
        <div className={styles.core}>
          <span className={styles.mark}>c/</span>
          <div><strong>care/fully CRM</strong><small>One connected clinic workspace</small></div>
          <span className={styles.coreTag}>CORE PLATFORM</span>
        </div>
        <div className={styles.trunk} />
        <div className={styles.lanes}>
          {lanes.map((lane) => (
            <section className={styles.lane} key={lane.number}>
              <div className={styles.laneHead}>
                <span>{lane.number}</span>
                <div><h2>{lane.title}</h2><p>{lane.subtitle}</p></div>
              </div>
              <div className={styles.nodes}>
                {lane.nodes.map((node, index) => (
                  <div className={styles.nodeWrap} key={node.title}>
                    <button
                      type="button"
                      className={[styles.node, selected.title === node.title ? styles.active : ""].join(" ")}
                      onClick={() => setSelected(node)}
                      aria-pressed={selected.title === node.title}
                    >
                      <i /><span>{node.title}</span><b>↗</b>
                    </button>
                    {index < lane.nodes.length - 1 && <span className={styles.arrow}>↓</span>}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>

      <section className={styles.detail} aria-live="polite">
        <div><span>SELECTED WORKSPACE</span><h2>{selected.title}</h2><p>{selected.text}</p></div>
        <a href={selected.href}>Open workspace <b>↗</b></a>
      </section>

      <section className={styles.flowSection}>
        <div className={styles.flowIntro}>
          <p className={styles.eyebrow}>HOW THE SYSTEM CONNECTS</p>
          <h2>Follow the flow<br /><em>across the clinic.</em></h2>
        </div>
        <div className={styles.flowList}>
          {flow.map((item, index) => (
            <article className={styles.flowRow} key={item[0] + item[1]}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{item[0]}</strong><b>→</b><strong>{item[1]}</strong>
              <small>{item[2]}</small>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.foundation}>
        <p className={styles.eyebrow}>SHARED FOUNDATION</p>
        <h2>Every workspace shares the same foundation.</h2>
        <div className={styles.foundationGrid}>
          <article><b>Identity & permissions</b><span>Sign-in, sessions, roles and permission checks.</span></article>
          <article><b>Tenant isolation</b><span>Clinic-scoped access enforced by PostgreSQL RLS.</span></article>
          <article><b>Audit & history</b><span>Traceable activity, appointment history and lead stage history.</span></article>
          <article><b>Shared records</b><span>Patients, appointments, services, branches and inventory remain connected.</span></article>
        </div>
      </section>

      <footer className={styles.footer}>
        <span className={styles.brand}>care<span>/</span>fully</span>
        <p>Public product roadmap · No patient or live clinic records are displayed.</p>
        <a href="https://github.com/waleed260/healthcare-platform" target="_blank" rel="noreferrer">View project on GitHub ↗</a>
      </footer>
    </main>
  );
}
