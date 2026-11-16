import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy | care/fully",
  description: "How care/fully handles clinic and patient data.",
};

// Factual summary of what the platform does with data; it is not legal advice.
export default function PrivacyPolicyPage() {
  return (
    <main className="landing-page lp-legal">
      <nav className="lp-nav shell" aria-label="Primary navigation">
        <Link className="wordmark" href="/">care<span>/</span>fully</Link>
        <div className="lp-nav-links"><Link className="lp-nav-signin" href="/login">Sign in</Link></div>
      </nav>
      <article className="shell lp-legal-body">
        <p className="lp-eyebrow">Privacy</p>
        <h1>How care/fully handles data</h1>
        <p>care/fully is operated for clinics. Each clinic is the controller of its own patient records; care/fully processes them on the clinic&rsquo;s behalf to run its website, bookings, queue, records and billing.</p>
        <h2>What is stored</h2>
        <ul>
          <li>Clinic staff accounts, roles and sign-in sessions.</li>
          <li>Patient records that clinic staff enter: contact details, appointments, clinical notes, documents, invoices.</li>
          <li>Public booking and enquiry forms submitted on a clinic&rsquo;s website, together with the consent given on the form.</li>
          <li>An audit trail of who accessed or changed protected records.</li>
        </ul>
        <h2>How it is protected</h2>
        <ul>
          <li>Every clinic&rsquo;s data is isolated at the database layer; one clinic can never query another&rsquo;s rows.</li>
          <li>Sign-in uses hashed session tokens, optional two-factor authentication and lockout after repeated failures.</li>
          <li>Uploaded files are checked for their real type and scanned before they are served.</li>
          <li>Patient photos appear on a clinic website only after the patient&rsquo;s recorded consent and staff approval.</li>
        </ul>
        <h2>Your rights</h2>
        <p>Patients can ask their clinic to export or delete their record; the clinic handles that request inside the platform and the action is logged. Clinics can request a full export of their own data at any time.</p>
        <h2>Contact</h2>
        <p>Questions about this summary or a data request: <a href="mailto:hello@carefully.health?subject=Privacy%20request">hello@carefully.health</a>.</p>
      </article>
    </main>
  );
}
