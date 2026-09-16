"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

type Branch = { id: string; name: string; address: Record<string, string> | null; timezone: string };
type Service = { id: string; name: string; short_description: string | null; duration_minutes: number; branch_id: string };
type Doctor = { id: string; public_name: string; specialty: string | null; branch_id: string; service_id: string };
type Catalog = { clinic: { name: string; timezone: string }; branches: Branch[]; services: Service[]; doctors: Doctor[] };
type BookingResult = { reference: string; status: string; management_secret: string };

function dateString(daysFromToday: number): string {
  const date = new Date();
  date.setDate(date.getDate() + daysFromToday);
  return date.toISOString().slice(0, 10);
}

async function payloadOrError(response: Response): Promise<any> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? "Something went wrong. Please try again.");
  return payload.data;
}

export default function BookingPage() {
  const params = useParams<{ clinicSlug: string }>();
  const slug = decodeURIComponent(params.clinicSlug);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
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

  const branchServices = useMemo(() => catalog?.services.filter((service) => service.branch_id === branchId) ?? [], [catalog, branchId]);
  const doctors = useMemo(() => catalog?.doctors.filter((doctor) => doctor.branch_id === branchId && doctor.service_id === serviceId) ?? [], [catalog, branchId, serviceId]);

  useEffect(() => {
    if (branchServices.length && !branchServices.some((service) => service.id === serviceId)) setServiceId(branchServices[0].id);
  }, [branchServices, serviceId]);

  useEffect(() => {
    if (doctorId && !doctors.some((doctor) => doctor.id === doctorId)) setDoctorId("");
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

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSlot) { setError("Choose an appointment time first."); return; }
    setSubmitting(true); setError(null);
    try {
      const data = await payloadOrError(await fetch("/api/v1/public/bookings", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID(), "X-Clinic-Slug": slug }, body: JSON.stringify({ branch_id: branchId, service_id: serviceId, doctor_id: doctorId || null, starts_at: selectedSlot, ...form }) }));
      setConfirmation(data as BookingResult);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The booking could not be submitted."); }
    finally { setSubmitting(false); }
  }

  if (loading) return <main className="booking-page"><div className="booking-shell"><p className="eyebrow">LOADING CLINIC</p><div className="booking-loading" role="status">Preparing appointment options…</div></div></main>;
  if (!catalog) return <main className="booking-page"><div className="booking-shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="booking-alert" role="alert">{error ?? "This clinic is not available."}</div></div></main>;
  if (confirmation) return <main className="booking-page"><div className="booking-shell booking-confirmation"><p className="eyebrow"><span className="eyebrow-dot" /> REQUEST RECEIVED</p><h1>You&apos;re on the <em>list.</em></h1><p>Your clinic will review the request. Keep these details somewhere safe if you need to manage it later.</p><div className="reference-card"><span>REFERENCE</span><strong>{confirmation.reference}</strong><small>Status: {confirmation.status.replaceAll("_", " ")}</small><code>{confirmation.management_secret}</code></div><Link className="button button-primary" href="/">Return home <span>↗</span></Link></div></main>;

  return <main className="booking-page"><div className="booking-shell"><header className="booking-header"><Link className="wordmark" href="/">care<span>/</span>fully</Link><span className="booking-secure">PUBLIC BOOKING · {catalog.clinic.timezone}</span></header><div className="booking-layout"><section className="booking-intro"><p className="eyebrow"><span className="eyebrow-dot" /> {catalog.clinic.name}</p><h1>Make time for <em>care.</em></h1><p>Choose a service, find a calm opening, and send your request in under three minutes.</p><div className="booking-note"><span>01</span><span>Displayed times are in your clinic&apos;s local timezone.</span></div></section><form className="booking-form" onSubmit={submitBooking} aria-label="Request an appointment"><fieldset><legend>Find your opening</legend><label>Branch<select value={branchId} onChange={(event) => setBranchId(event.target.value)}>{catalog.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></label><label>Service<select value={serviceId} onChange={(event) => setServiceId(event.target.value)}>{branchServices.map((service) => <option key={service.id} value={service.id}>{service.name} · {service.duration_minutes} min</option>)}</select></label><label>Preferred doctor <span className="optional">optional</span><select value={doctorId} onChange={(event) => setDoctorId(event.target.value)}><option value="">Any available doctor</option>{doctors.map((doctor) => <option key={doctor.id} value={doctor.id}>{doctor.public_name}{doctor.specialty ? ` · ${doctor.specialty}` : ""}</option>)}</select></label><label>Date<input type="date" min={dateString(1)} max={dateString(89)} value={day} onChange={(event) => setDay(event.target.value)} /></label><div className="slot-label"><span>Available times</span><span>{loadingSlots ? "Checking…" : `${slots.length} openings`}</span></div><div className="slot-grid" aria-live="polite">{!loadingSlots && slots.length === 0 && <p className="slot-empty">No openings on this day. Try another date.</p>}{slots.map((slot) => <button type="button" className={selectedSlot === slot ? "slot selected" : "slot"} key={slot} onClick={() => setSelectedSlot(slot)}>{new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(slot))}</button>)}</div></fieldset><fieldset><legend>Your details</legend><label>Full name<input required maxLength={160} value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} placeholder="Your name" /></label><label>Email <span className="optional">optional</span><input type="email" maxLength={320} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} placeholder="you@example.com" /></label><label>Phone <span className="optional">optional</span><input maxLength={40} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} placeholder="A number the clinic can reach" /></label></fieldset>{error && <div className="booking-alert" role="alert">{error}</div>}<button className="button button-primary booking-submit" disabled={submitting || !selectedSlot} type="submit">{submitting ? "Sending request…" : "Request appointment"}<span>→</span></button><p className="booking-legal">By continuing, you share these details with {catalog.clinic.name} for appointment coordination. This is a request, not a confirmed appointment.</p></form></div></div></main>;
}
