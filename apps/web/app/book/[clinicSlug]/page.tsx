"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

type Branch = { id: string; name: string; address: Record<string, string> | null; timezone: string };
type Service = { id: string; name: string; short_description: string | null; duration_minutes: number; branch_id: string; price_minor?: number; currency?: string };
type Doctor = { id: string; public_name: string; specialty: string | null; branch_id: string; service_id: string };
type Catalog = { clinic: { name: string; timezone: string }; branches: Branch[]; services: Service[]; doctors: Doctor[] };
type BookingResult = { reference: string; status: string; management_secret: string };

function dateString(daysFromToday: number): string {
  const date = new Date();
  date.setDate(date.getDate() + daysFromToday);
  return date.toISOString().slice(0, 10);
}

function formatTime(iso: string) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}

function formatDate(iso: string) {
  return new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" }).format(new Date(iso));
}

async function payloadOrError(response: Response): Promise<any> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? "Something went wrong. Please try again.");
  return payload.data;
}

const STEPS = ["Service", "Provider", "Date & Time", "Your Details", "Confirm"] as const;

export default function BookingPage() {
  const params = useParams<{ clinicSlug: string }>();
  const slug = decodeURIComponent(params.clinicSlug);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [step, setStep] = useState(1);
  const [branchId, setBranchId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [day, setDay] = useState(dateString(1));
  const [slots, setSlots] = useState<string[]>([]);
  const [selectedSlot, setSelectedSlot] = useState("");
  const [form, setForm] = useState({ full_name: "", email: "", phone: "" });
  const [loading, setLoading] = useState(true);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<BookingResult | null>(null);

  useEffect(() => {
    void fetch(`/api/v1/public/catalog?clinic_slug=${encodeURIComponent(slug)}`, { cache: "no-store" })
      .then(payloadOrError)
      .then((data: Catalog) => {
        setCatalog(data);
        setBranchId(data.branches[0]?.id ?? "");
        setServiceId(data.services[0]?.id ?? "");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "The clinic could not be loaded."))
      .finally(() => setLoading(false));
  }, [slug]);

  const branchServices = useMemo(() => catalog?.services.filter((s) => s.branch_id === branchId) ?? [], [catalog, branchId]);
  const doctors = useMemo(() => catalog?.doctors.filter((d) => d.branch_id === branchId && d.service_id === serviceId) ?? [], [catalog, branchId, serviceId]);
  const selectedBranch = useMemo(() => catalog?.branches.find((b) => b.id === branchId), [catalog, branchId]);
  const selectedService = useMemo(() => catalog?.services.find((s) => s.id === serviceId), [catalog, serviceId]);
  const selectedDoctor = useMemo(() => catalog?.doctors.find((d) => d.id === doctorId), [catalog, doctorId]);

  useEffect(() => {
    if (branchServices.length && !branchServices.some((s) => s.id === serviceId)) setServiceId(branchServices[0].id);
  }, [branchServices, serviceId]);

  useEffect(() => {
    if (doctorId && !doctors.some((d) => d.id === doctorId)) setDoctorId("");
  }, [doctorId, doctors]);

  useEffect(() => {
    if (!branchId || !serviceId || !day) return;
    const controller = new AbortController();
    setLoadingSlots(true);
    setError(null);
    setSelectedSlot("");
    void fetch(`/api/v1/public/availability?clinic_slug=${encodeURIComponent(slug)}&branch_id=${branchId}&service_id=${serviceId}&from_date=${day}&to_date=${day}${doctorId ? `&doctor_id=${doctorId}` : ""}`, { signal: controller.signal, cache: "no-store" })
      .then(payloadOrError)
      .then((data: { slots: string[] }) => setSlots(data.slots))
      .catch((reason: unknown) => { if (reason instanceof DOMException && reason.name === "AbortError") return; setError(reason instanceof Error ? reason.message : "Availability could not be loaded."); })
      .finally(() => setLoadingSlots(false));
    return () => controller.abort();
  }, [branchId, serviceId, doctorId, day, slug]);

  function goNext() {
    if (step === 1 && !serviceId) { setError("Choose a service to continue."); return; }
    if (step === 2) { setStep(3); return; }
    if (step === 3 && !selectedSlot) { setError("Choose an appointment time."); return; }
    if (step === 4 && !form.full_name.trim()) { setError("Please enter your name."); return; }
    setError(null);
    if (step === 1 && doctors.length === 0) setStep(3);
    else setStep(step + 1);
  }

  function goBack() {
    setError(null);
    if (step === 3 && doctors.length === 0) setStep(1);
    else setStep(step - 1);
  }

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const data = await payloadOrError(await fetch("/api/v1/public/bookings", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID(), "X-Clinic-Slug": slug },
        body: JSON.stringify({ branch_id: branchId, service_id: serviceId, doctor_id: doctorId || null, starts_at: selectedSlot, ...form }),
      }));
      setConfirmation(data as BookingResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The booking could not be submitted.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <main className="booking-page"><div className="booking-shell"><p className="eyebrow">LOADING CLINIC</p><div className="booking-loading" role="status">Preparing appointment options…</div></div></main>;
  if (!catalog) return <main className="booking-page"><div className="booking-shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="booking-alert" role="alert">{error ?? "This clinic is not available."}</div></div></main>;

  if (confirmation) return (
    <main className="booking-page">
      <div className="booking-shell booking-confirmation">
        <p className="eyebrow"><span className="eyebrow-dot" /> REQUEST RECEIVED</p>
        <h1>You&apos;re on the <em>list.</em></h1>
        <p>Your clinic will review the request. Keep these details somewhere safe if you need to manage it later.</p>
        <div className="reference-card">
          <span>REFERENCE</span>
          <strong>{confirmation.reference}</strong>
          <small>Status: {confirmation.status.replaceAll("_", " ")}</small>
          <code>{confirmation.management_secret}</code>
        </div>
        <div className="booking-summary-card">
          <p className="eyebrow">WHAT YOU BOOKED</p>
          {selectedBranch && <p><strong>Branch:</strong> {selectedBranch.name}</p>}
          {selectedService && <p><strong>Service:</strong> {selectedService.name} · {selectedService.duration_minutes} min</p>}
          {selectedDoctor && <p><strong>Provider:</strong> {selectedDoctor.public_name}</p>}
          {selectedSlot && <p><strong>When:</strong> {formatDate(selectedSlot)} at {formatTime(selectedSlot)}</p>}
        </div>
        <Link className="button button-primary" href="/">Return home <span>↗</span></Link>
      </div>
    </main>
  );

  return (
    <main className="booking-page">
      <div className="booking-shell">
        <header className="booking-header">
          <Link className="wordmark" href="/">care<span>/</span>fully</Link>
          <span className="booking-secure">PUBLIC BOOKING · {catalog.clinic.timezone}</span>
        </header>

        <div className="booking-steps">
          <p className="eyebrow"><span className="eyebrow-dot" /> {catalog.clinic.name}</p>
          <h1>Make time for <em>care.</em></h1>
          <div className="booking-step-indicator" role="navigation" aria-label="Booking progress">
            {STEPS.map((label, index) => (
              <div key={label} className={`booking-step-dot${step === index + 1 ? " active" : ""}${step > index + 1 ? " done" : ""}`}>
                <span className="booking-step-number">{step > index + 1 ? "✓" : index + 1}</span>
                <span className="booking-step-label">{label}</span>
              </div>
            ))}
          </div>
        </div>

        {error && <div className="booking-alert" role="alert">{error}</div>}

        {step === 1 && (
          <section className="booking-step-panel" aria-label="Choose a service">
            {catalog.branches.length > 1 && (
              <>
                <h2>Choose a branch</h2>
                <div className="booking-card-grid">
                  {catalog.branches.map((branch) => (
                    <button key={branch.id} type="button" className={`booking-card${branchId === branch.id ? " selected" : ""}`} onClick={() => setBranchId(branch.id)}>
                      <strong>{branch.name}</strong>
                      <small>{branch.timezone}</small>
                    </button>
                  ))}
                </div>
              </>
            )}
            <h2>Choose a service</h2>
            <div className="booking-card-grid">
              {branchServices.map((service) => (
                <button key={service.id} type="button" className={`booking-card${serviceId === service.id ? " selected" : ""}`} onClick={() => setServiceId(service.id)}>
                  <strong>{service.name}</strong>
                  <small>{service.duration_minutes} min{service.short_description ? ` · ${service.short_description}` : ""}</small>
                </button>
              ))}
              {branchServices.length === 0 && <p className="booking-empty">No services available at this branch.</p>}
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="booking-step-panel" aria-label="Choose a provider">
            <h2>Choose a provider <span className="optional">optional</span></h2>
            <div className="booking-card-grid">
              <button type="button" className={`booking-card${!doctorId ? " selected" : ""}`} onClick={() => setDoctorId("")}>
                <div className="booking-avatar">?</div>
                <strong>Any available</strong>
                <small>First available provider</small>
              </button>
              {doctors.map((doctor) => (
                <button key={doctor.id} type="button" className={`booking-card${doctorId === doctor.id ? " selected" : ""}`} onClick={() => setDoctorId(doctor.id)}>
                  <div className="booking-avatar">{doctor.public_name.slice(0, 1)}</div>
                  <strong>{doctor.public_name}</strong>
                  {doctor.specialty && <small>{doctor.specialty}</small>}
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="booking-step-panel" aria-label="Choose date and time">
            <h2>Pick a date</h2>
            <input type="date" className="booking-date-input" min={dateString(1)} max={dateString(89)} value={day} onChange={(e) => setDay(e.target.value)} />
            <h2>Available times <small>{loadingSlots ? "Checking…" : `${slots.length} openings`}</small></h2>
            <div className="slot-grid" aria-live="polite">
              {!loadingSlots && slots.length === 0 && <p className="slot-empty">No openings on this day. Try another date.</p>}
              {slots.map((slot) => (
                <button type="button" className={selectedSlot === slot ? "slot selected" : "slot"} key={slot} onClick={() => setSelectedSlot(slot)}>
                  {formatTime(slot)}
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 4 && (
          <section className="booking-step-panel" aria-label="Your details">
            <h2>Your details</h2>
            <div className="booking-fields">
              <label>Full name <input required maxLength={160} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Your name" /></label>
              <label>Email <span className="optional">optional</span><input type="email" maxLength={320} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" /></label>
              <label>Phone <span className="optional">optional</span><input maxLength={40} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="A number the clinic can reach" /></label>
            </div>
          </section>
        )}

        {step === 5 && (
          <form className="booking-step-panel" onSubmit={submitBooking} aria-label="Confirm your booking">
            <h2>Confirm your booking</h2>
            <div className="booking-summary-card">
              <div className="booking-summary-row"><span>Branch</span><strong>{selectedBranch?.name ?? "—"}</strong></div>
              <div className="booking-summary-row"><span>Service</span><strong>{selectedService?.name ?? "—"} · {selectedService?.duration_minutes ?? 0} min</strong></div>
              <div className="booking-summary-row"><span>Provider</span><strong>{selectedDoctor?.public_name ?? "Any available"}</strong></div>
              <div className="booking-summary-row"><span>When</span><strong>{selectedSlot ? `${formatDate(selectedSlot)} at ${formatTime(selectedSlot)}` : "—"}</strong></div>
              <div className="booking-summary-row"><span>Name</span><strong>{form.full_name || "—"}</strong></div>
              {form.email && <div className="booking-summary-row"><span>Email</span><strong>{form.email}</strong></div>}
              {form.phone && <div className="booking-summary-row"><span>Phone</span><strong>{form.phone}</strong></div>}
            </div>
            <button className="button button-primary booking-submit" disabled={submitting} type="submit">
              {submitting ? "Sending request…" : "Request appointment"}<span>→</span>
            </button>
            <p className="booking-legal">By continuing, you share these details with {catalog.clinic.name} for appointment coordination. This is a request, not a confirmed appointment.</p>
          </form>
        )}

        <div className="booking-nav">
          {step > 1 && <button type="button" className="button button-secondary" onClick={goBack}>← Back</button>}
          {step < 5 && <button type="button" className="button button-primary" onClick={goNext}>Next →</button>}
        </div>
      </div>
    </main>
  );
}
