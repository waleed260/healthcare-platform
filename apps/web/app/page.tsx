import Link from "next/link";
import LandingMotion from "./landing-motion";

const features = [
  {
    id: "website",
    eyebrow: "WEBSITE & BOOKING",
    title: "Your clinic's front door",
    heading: <>Your clinic&#8217;s<br /><em>front door.</em></>,
    body: "Publish a calm, credible clinic website and let patients book real availability — without handing your team a second system to manage.",
    points: ["Website builder with live preview", "Real-time slot booking", "Patient-facing service catalog"],
    align: "left" as const,
  },
  {
    id: "operations",
    eyebrow: "SCHEDULE & QUEUE",
    title: "Run the day, not the paperwork",
    heading: <>Run the day,<br /><em>not the paperwork.</em></>,
    body: "A shared view of who is waiting, what comes next, and where every appointment stands — so the team moves together without extra messages.",
    points: ["Live queue with status updates", "Calendar with drag-and-drop", "Role-based team views"],
    align: "right" as const,
  },
  {
    id: "followups",
    eyebrow: "CRM & FOLLOW-UPS",
    title: "Follow through on every visit",
    heading: <>Follow through on<br /><em>every visit.</em></>,
    body: "Turn the small promises after each appointment into visible, assignable work. Patient context, care teams, notes, and consent stay close to the work.",
    points: ["Assignable follow-up tasks", "Full patient timeline", "Treatment plans & consent tracking"],
    align: "left" as const,
  },
];

const metrics = [
  { value: "2hrs", label: "Saved per clinic, per day" },
  { value: "99.9%", label: "Platform uptime" },
  { value: "<2min", label: "Average setup time" },
  { value: "0", label: "Spreadsheets needed" },
];

const securityItems = [
  { icon: "shield", title: "Tenant isolation", desc: "Every clinic's data is enforced at the database layer, not just in application code." },
  { icon: "lock", title: "MFA-aware access", desc: "Protected workspace actions require an authenticated, verified session." },
  { icon: "eye", title: "Audit trail", desc: "Meaningful staff actions are recorded with context, outcome, and timestamp." },
  { icon: "file", title: "Private files", desc: "Documents remain behind scoped access with scan status verification." },
];

const testimonials = [
  { quote: "We went from three spreadsheets and a WhatsApp group to one screen. The morning is calmer now.", name: "Dr. Amira Hassan", role: "Family Medicine", clinic: "Noor Clinic" },
  { quote: "My staff used to call patients one by one for follow-ups. Now it's a task list that actually gets done.", name: "Dr. Ravi Menon", role: "General Practice", clinic: "Greenleaf Medical" },
  { quote: "The booking page alone saved us two hours a day on the phone. Patients love choosing their own time.", name: "Dr. Sara Vidal", role: "Dermatology", clinic: "Vidal Skin Centre" },
];

const faqs = [
  ["Who is care/fully for?", "Independent doctors and small clinics that want one dependable workspace for their public site and daily operations — without the complexity of enterprise software."],
  ["How much does it cost?", "We are currently in early access. Request a demo and we will walk you through pricing that fits your clinic size."],
  ["Does it replace our clinical record?", "No. care/fully focuses on the clinic experience around your clinical work: your website, booking, schedule, queue, CRM, and follow-up operations."],
  ["Can our team work with different permissions?", "Yes. Access is scoped by clinic, branch, role, and permission. The API enforces every protected action."],
  ["How long does setup take?", "Most clinics are up and running within a day. Onboarding walks you through services, team roles, and your public site step by step."],
  ["Can I migrate from another system?", "We support importing patient records and service catalogs. Our team will help you transfer what matters."],
  ["Is my patient data safe?", "Absolutely. Tenant isolation is enforced at the database layer, sessions are MFA-aware, files are scanned, and every protected action is audited."],
  ["Is there a template gallery?", "We ship one polished, fully renderable clinic template today. More are coming — we add them when they meet the same standard."],
];

const footerLinks = {
  product: [
    { label: "Website Builder", href: "#website" },
    { label: "Booking", href: "#website" },
    { label: "Queue & Schedule", href: "#operations" },
    { label: "CRM", href: "#followups" },
    { label: "Follow-ups", href: "#followups" },
  ],
  company: [
    { label: "Contact", href: "mailto:hello@carefully.health" },
    { label: "Privacy", href: "/privacy" },
  ],
};

function DashboardPreview() {
  return (
    <div className="lp-dash" aria-label="Synthetic clinic dashboard preview">
      <div className="lp-dash-sidebar">
        <span className="lp-dash-mark">c/</span>
        <span className="lp-dash-nav-item lp-dash-nav-active">Overview</span>
        <span className="lp-dash-nav-item">Schedule</span>
        <span className="lp-dash-nav-item">Patients</span>
        <span className="lp-dash-nav-item">Queue</span>
        <span className="lp-dash-nav-item">Follow-ups</span>
      </div>
      <div className="lp-dash-main">
        <div className="lp-dash-topbar">
          <span>Monday · clinic time</span>
          <b>VC</b>
        </div>
        <h3>Good morning, <i>team.</i></h3>
        <div className="lp-dash-kpis">
          <span><small>Today</small><strong>12</strong><em>appointments</em></span>
          <span><small>Waiting</small><strong>03</strong><em>in queue</em></span>
          <span><small>Follow-ups</small><strong>07</strong><em>due now</em></span>
        </div>
        <div className="lp-dash-schedule">
          <div><small>Your day</small><b>Today&apos;s schedule</b></div>
          <p><time>09:30</time><strong>New patient consultation</strong><em>confirmed</em></p>
          <p><time>10:15</time><strong>Review · Dr. Vale</strong><em>in 45 min</em></p>
          <p><time>11:00</time><strong>Follow-up appointment</strong><em>requested</em></p>
        </div>
      </div>
    </div>
  );
}

function WebsitePreview() {
  return (
    <div className="lp-site-preview" aria-label="Synthetic published clinic website preview">
      <div className="lp-site-browser">
        <span /><span /><span />
        <em>vale-clinic.example</em>
      </div>
      <div className="lp-site-body">
        <small>VALE FAMILY CLINIC</small>
        <h3>Care that<br /><i>keeps pace.</i></h3>
        <p>Thoughtful primary care for busy lives.</p>
        <button type="button">Book a visit</button>
        <div className="lp-site-sun" />
      </div>
    </div>
  );
}

function PhonePreview() {
  return (
    <div className="lp-phone" aria-label="Synthetic patient booking preview">
      <div className="lp-phone-notch" />
      <div className="lp-phone-screen">
        <span className="lp-phone-brand">care/fully</span>
        <small>BOOK A VISIT</small>
        <h3>Choose a time<br /><i>that works.</i></h3>
        <div className="lp-phone-doctor">
          <span>DV</span>
          <p><b>Dr. Vale</b><small>General medicine</small></p>
        </div>
        <div className="lp-phone-slots">
          <b>Today</b>
          <span>09:30</span>
          <span className="lp-slot-selected">10:15</span>
          <span>11:00</span>
        </div>
        <button type="button">Continue <i>→</i></button>
      </div>
    </div>
  );
}

function QueuePreview() {
  return (
    <div className="lp-queue-preview" aria-label="Synthetic queue preview">
      <div className="lp-queue-header"><small>LIVE QUEUE</small><b>3 waiting</b></div>
      <div className="lp-queue-row"><span className="lp-queue-num">01</span><div><b>Amelia R.</b><small>Consultation · Dr. Vale</small></div><em className="lp-queue-status-waiting">waiting</em></div>
      <div className="lp-queue-row"><span className="lp-queue-num">02</span><div><b>Jon M.</b><small>Follow-up · Dr. Hassan</small></div><em className="lp-queue-status-active">in room</em></div>
      <div className="lp-queue-row"><span className="lp-queue-num">03</span><div><b>Sara K.</b><small>New patient · Dr. Vale</small></div><em className="lp-queue-status-next">next</em></div>
    </div>
  );
}

function FollowUpPreview() {
  return (
    <div className="lp-followup-preview" aria-label="Synthetic follow-up preview">
      <div className="lp-followup-header"><small>FOLLOW-UPS DUE</small><b>Today</b></div>
      <div className="lp-followup-item"><span className="lp-followup-dot lp-dot-urgent" /><div><b>Check in with Amelia R.</b><small>Post-procedure · 3 days ago</small></div><em>assigned to Dr. Vale</em></div>
      <div className="lp-followup-item"><span className="lp-followup-dot lp-dot-normal" /><div><b>Lab results review — Jon M.</b><small>Blood work · 5 days ago</small></div><em>assigned to Dr. Hassan</em></div>
      <div className="lp-followup-item"><span className="lp-followup-dot lp-dot-done" /><div><b>Prescription renewal — Layla F.</b><small>Monthly refill · completed</small></div><em>done</em></div>
    </div>
  );
}

function SecurityIcon({ type }: { type: string }) {
  if (type === "shield") return <svg className="lp-sec-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2l8 4v6c0 5.25-3.5 8.25-8 10-4.5-1.75-8-4.75-8-10V6l8-4z" /></svg>;
  if (type === "lock") return <svg className="lp-sec-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" /></svg>;
  if (type === "eye") return <svg className="lp-sec-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" /><circle cx="12" cy="12" r="3" /></svg>;
  return <svg className="lp-sec-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" /><path d="M9 15h6M9 11h6" /></svg>;
}

export default function HomePage() {
  return (
    <main className="landing-page">
      <LandingMotion />
      <div className="lp-scroll-progress" aria-hidden="true" />

      {/* Nav */}
      <nav className="lp-nav shell" aria-label="Primary navigation">
        <Link className="wordmark" href="/">care<span>/</span>fully</Link>
        <input type="checkbox" id="lp-menu-toggle" className="lp-menu-checkbox" aria-hidden="true" />
        <label htmlFor="lp-menu-toggle" className="lp-hamburger" aria-label="Toggle navigation menu">
          <span /><span /><span />
        </label>
        <div className="lp-nav-links">
          <a href="#product">Product</a>
          <a href="#how-it-works">How it works</a>
          <a href="#security">Security</a>
          <a href="#pricing">Pricing</a>
          <Link className="lp-nav-signin" href="/login">Sign in</Link>
          <Link className="lp-nav-cta" href="#pricing">Request a demo <span>→</span></Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="lp-hero shell" aria-labelledby="hero-title">
        <div className="lp-hero-copy" data-reveal>
          <p className="lp-eyebrow"><span className="lp-eyebrow-dot" /> Clinic operations, with room to breathe</p>
          <h1 id="hero-title">Make care feel <em>well run.</em></h1>
          <p className="lp-hero-lede">Website, booking, queue, CRM, and follow-ups — one workspace for your entire clinic.</p>
          <div className="lp-hero-actions">
            <Link className="lp-btn lp-btn-primary" href="/login">Start your workspace <span>→</span></Link>
            <a className="lp-btn-text" href="#product">See how it works <span>↓</span></a>
          </div>
        </div>
        <div className="lp-hero-visual" data-reveal>
          <DashboardPreview />
        </div>
      </section>

      {/* Trust bar */}
      <section className="lp-trust-bar" aria-label="Platform statistics" data-reveal>
        <div className="shell lp-trust-inner">
          {metrics.map((m) => (
            <div key={m.label} className="lp-trust-stat lp-stagger">
              <strong data-count={m.value}>{m.value}</strong>
              <span>{m.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Product showcase */}
      <section id="product" aria-labelledby="product-title">
        <div className="lp-product-intro shell" data-reveal>
          <p className="lp-eyebrow">One connected workspace</p>
          <h2 id="product-title">The front door,<br /><em>the day itself.</em></h2>
          <p className="lp-product-lede">care/fully keeps the public experience and the private work in the same rhythm. Patients get a clear path in. Teams get a clear view of what comes next.</p>
        </div>

        {features.map((f, i) => (
          <div key={f.id} id={f.id} className={`lp-showcase lp-showcase-${f.align} lp-showcase-${i + 1}`} data-reveal>
            <div className="shell lp-showcase-inner">
              <div className="lp-showcase-copy">
                <p className="lp-eyebrow">{f.eyebrow}</p>
                <h3>{f.heading}</h3>
                <p>{f.body}</p>
                <ul className="lp-showcase-points">
                  {f.points.map((p) => <li key={p}><span>✓</span> {p}</li>)}
                </ul>
              </div>
              <div className="lp-showcase-visual">
                {i === 0 && <><WebsitePreview /><PhonePreview /></>}
                {i === 1 && <><DashboardPreview /><QueuePreview /></>}
                {i === 2 && <FollowUpPreview />}
              </div>
            </div>
          </div>
        ))}
      </section>

      {/* How it works */}
      <section className="lp-how" id="how-it-works" aria-labelledby="how-title">
        <div className="shell">
          <div className="lp-section-header" data-reveal>
            <p className="lp-eyebrow">A simple handoff</p>
            <h2 id="how-title">From setup to<br /><em>steady days.</em></h2>
          </div>
          <div className="lp-steps" data-reveal>
            <article className="lp-step lp-stagger">
              <div className="lp-step-number">01</div>
              <h3>Onboard</h3>
              <p>Set up your clinic, services, team roles, and the shape of your day. Most clinics finish in under a day.</p>
            </article>
            <div className="lp-step-line" aria-hidden="true" />
            <article className="lp-step lp-stagger">
              <div className="lp-step-number">02</div>
              <h3>Publish</h3>
              <p>Launch your clinic website and booking page. Patients see real availability and book without a phone call.</p>
            </article>
            <div className="lp-step-line" aria-hidden="true" />
            <article className="lp-step lp-stagger">
              <div className="lp-step-number">03</div>
              <h3>Run the day</h3>
              <p>Move from request to appointment to follow-up with less context switching and fewer dropped balls.</p>
            </article>
          </div>
        </div>
      </section>

      {/* Security */}
      <section className="lp-security shell" id="security" aria-labelledby="security-title">
        <div className="lp-section-header" data-reveal>
          <p className="lp-eyebrow">Quietly serious about the foundation</p>
          <h2 id="security-title">Trust is part of<br /><em>the interface.</em></h2>
          <p className="lp-section-lede">These are product foundations, not marketing badges.</p>
        </div>
        <div className="lp-security-grid" data-reveal>
          {securityItems.map((item) => (
            <article key={item.title} className="lp-sec-card lp-stagger">
              <SecurityIcon type={item.icon} />
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
            </article>
          ))}
        </div>
      </section>

      {/* Testimonials */}
      <section className="lp-testimonials" aria-labelledby="testimonials-title">
        <div className="shell">
          <div className="lp-section-header" data-reveal>
            <p className="lp-eyebrow">From clinics like yours</p>
            <h2 id="testimonials-title">The day feels<br /><em>different now.</em></h2>
          </div>
          <div className="lp-testimonial-grid" data-reveal>
            {testimonials.map((t) => (
              <article key={t.name} className="lp-testimonial-card lp-stagger">
                <blockquote>&ldquo;{t.quote}&rdquo;</blockquote>
                <footer>
                  <div className="lp-testimonial-avatar">{t.name.split(" ").map((n) => n[0]).join("")}</div>
                  <div>
                    <strong>{t.name}</strong>
                    <small>{t.role} · {t.clinic}</small>
                  </div>
                </footer>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="lp-pricing shell" id="pricing" aria-labelledby="pricing-title">
        <div className="lp-pricing-card" data-reveal>
          <p className="lp-eyebrow">EARLY ACCESS</p>
          <h2 id="pricing-title">Simple, transparent pricing.</h2>
          <p className="lp-pricing-desc">care/fully is currently in early access. Request a demo and we&#8217;ll walk you through plans that fit your clinic.</p>
          <div className="lp-pricing-features">
            <span>✓ Full platform access</span>
            <span>✓ Unlimited team members</span>
            <span>✓ Guided onboarding</span>
            <span>✓ No credit card required</span>
          </div>
          <div className="lp-pricing-actions">
            <Link className="lp-btn lp-btn-primary" href="/login">Request a demo <span>→</span></Link>
            <Link className="lp-btn-text" href="/login">Or sign in to your workspace <span>→</span></Link>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="lp-faq shell" aria-labelledby="faq-title">
        <div className="lp-section-header" data-reveal>
          <p className="lp-eyebrow">Good questions</p>
          <h2 id="faq-title">A little more<br /><em>clarity.</em></h2>
        </div>
        <div className="lp-faq-list" data-reveal>
          {faqs.map(([question, answer]) => (
            <details key={question}>
              <summary>{question}<span>+</span></summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="lp-final-cta" data-reveal>
        <div className="shell">
          <p className="lp-eyebrow">When the day feels full</p>
          <h2>Your clinic deserves<br /><em>a calmer day.</em></h2>
          <div className="lp-final-actions">
            <Link className="lp-btn lp-btn-light" href="/login">Request a demo <span>→</span></Link>
            <Link className="lp-btn-text-light" href="/login">Sign in to your workspace <span>→</span></Link>
          </div>
          <p className="lp-final-note">No credit card required · Set up in under a day</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="lp-footer">
        <div className="shell lp-footer-inner">
          <div className="lp-footer-brand">
            <span className="wordmark">care<span>/</span>fully</span>
            <p>Clinic operations, with room to breathe.</p>
          </div>
          <div className="lp-footer-col">
            <h4>Product</h4>
            {footerLinks.product.map((l) => <a key={l.label} href={l.href}>{l.label}</a>)}
          </div>
          <div className="lp-footer-col">
            <h4>Company</h4>
            {footerLinks.company.map((l) => l.href.startsWith("/") ? <Link key={l.label} href={l.href}>{l.label}</Link> : <a key={l.label} href={l.href}>{l.label}</a>)}
          </div>
        </div>
        <div className="shell lp-footer-bottom">
          <span>&copy; {new Date().getFullYear()} care/fully. All rights reserved.</span>
          <Link href="/privacy">Privacy Policy</Link>
        </div>
      </footer>
    </main>
  );
}
