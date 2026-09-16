"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

type SetupState = { completed: boolean; completed_at: string | null; ready_to_complete: boolean; steps: Record<string, boolean> };
type Branch = { id: string; name: string; code: string; timezone: string };
type Doctor = { id: string; public_name: string };
type Service = { id: string; name: string };
type Catalog = { branches: Branch[]; doctors: Doctor[]; services: Service[] };

const labels: Record<string, string> = {
  first_branch: "Create your first branch", branch_hours: "Set branch hours", doctor: "Add a doctor",
  service: "Create a service", doctor_assignment: "Assign a doctor to a branch", service_assignment: "Assign a service to a branch",
};

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function responseMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null) as { error?: { message?: string } } | null;
  return payload?.error?.message ?? "That setup action could not be completed.";
}

async function send(path: string, method: string, body?: unknown): Promise<void> {
  const response = await fetch(path, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw new Error(await responseMessage(response));
}

export default function OnboardingPage() {
  const [setup, setSetup] = useState<SetupState | null>(null);
  const [catalog, setCatalog] = useState<Catalog>({ branches: [], doctors: [], services: [] });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [branchForm, setBranchForm] = useState({ code: "main", name: "Main clinic", timezone: "UTC" });
  const [doctorName, setDoctorName] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [selectedBranch, setSelectedBranch] = useState("");
  const [selectedDoctor, setSelectedDoctor] = useState("");
  const [selectedService, setSelectedService] = useState("");

  const loadSetup = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const responses = await Promise.all([
        fetch("/api/v1/clinic/onboarding", { credentials: "include", cache: "no-store" }),
        fetch("/api/v1/branches", { credentials: "include", cache: "no-store" }),
        fetch("/api/v1/doctors", { credentials: "include", cache: "no-store" }),
        fetch("/api/v1/services", { credentials: "include", cache: "no-store" }),
      ]);
      for (const response of responses) if (!response.ok) throw new Error(await responseMessage(response));
      const [setupPayload, branchesPayload, doctorsPayload, servicesPayload] = await Promise.all(responses.map((response) => response.json()));
      const nextCatalog = { branches: branchesPayload.data ?? [], doctors: doctorsPayload.data ?? [], services: servicesPayload.data ?? [] } as Catalog;
      setSetup(setupPayload.data); setCatalog(nextCatalog);
      setSelectedBranch((value) => value || nextCatalog.branches[0]?.id || "");
      setSelectedDoctor((value) => value || nextCatalog.doctors[0]?.id || "");
      setSelectedService((value) => value || nextCatalog.services[0]?.id || "");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The setup status could not be loaded."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void loadSetup(); }, [loadSetup]);

  async function action(key: string, callback: () => Promise<void>) {
    setBusy(key); setError(null);
    try { await callback(); await loadSetup(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "That setup action could not be completed."); }
    finally { setBusy(null); }
  }

  function submitBranch(event: FormEvent) { event.preventDefault(); void action("branch", () => send("/api/v1/branches", "POST", { ...branchForm, address: {} })); }
  function submitHours(event: FormEvent) { event.preventDefault(); if (selectedBranch) void action("hours", () => send(`/api/v1/branches/${selectedBranch}/hours/0`, "PUT", { weekday: 0, interval_index: 0, opens_at: "09:00:00", closes_at: "17:00:00", is_closed: false })); }
  function submitDoctor(event: FormEvent) { event.preventDefault(); void action("doctor", () => send("/api/v1/doctors", "POST", { public_name: doctorName, consultation_duration_minutes: 30 })); }
  function submitService(event: FormEvent) { event.preventDefault(); void action("service", () => send("/api/v1/services", "POST", { name: serviceName, duration_minutes: 30, approval_mode: "staff_approval", price_mode: "contact", visibility: "public" })); }
  function submitDoctorAssignment(event: FormEvent) { event.preventDefault(); if (selectedBranch && selectedDoctor) void action("doctor-assignment", () => send(`/api/v1/branches/${selectedBranch}/doctors/${selectedDoctor}`, "POST")); }
  function submitServiceAssignment(event: FormEvent) { event.preventDefault(); if (selectedBranch && selectedService) void action("service-assignment", () => send(`/api/v1/branches/${selectedBranch}/services/${selectedService}`, "POST")); }
  async function completeSetup() { await action("complete", () => send("/api/v1/clinic/onboarding/complete", "POST")); }
  const step = (key: string) => Boolean(setup?.steps[key]);
  const buttonText = (key: string, label: string) => busy === key ? "Saving…" : label;

  const branchOptions = <><option value="">Choose a branch</option>{catalog.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</>;
  return <main className="setup-page"><div className="setup-panel">
    <header className="setup-header"><Link className="wordmark" href="/">care<span>/</span>fully</Link><Link className="text-link" href="/dashboard">Workspace <span>→</span></Link></header>
    <div className="setup-intro"><p className="eyebrow">CLINIC SETUP</p><h1>Make it <em>yours.</em></h1><p>Build the essentials in a few calm passes. Leave at any time; your progress is saved as you go.</p></div>
    {error && <div className="workspace-alert" role="alert"><span>{error}</span><button className="ghost-button" type="button" onClick={() => void loadSetup()}>Try again <span>↻</span></button></div>}
    {loading && <div className="dashboard-empty" role="status"><strong>Loading setup</strong><span>Checking your clinic workspace…</span></div>}
    {!loading && setup && <>
      <ol className="setup-steps" aria-label="Setup progress">{Object.entries(setup.steps).map(([key, complete]) => <li className={complete ? "setup-step complete" : "setup-step"} key={key}><span className="step-mark" aria-hidden="true">{complete ? "✓" : ""}</span><span>{labels[key] ?? key.replaceAll("_", " ")}</span><span className="step-state">{complete ? "Ready" : "To do"}</span></li>)}</ol>
      <section className="setup-actions-grid" aria-label="Setup actions">
        {!step("first_branch") && <form className="setup-card" onSubmit={submitBranch}><p className="eyebrow">01 · LOCATION</p><h2>Open your first branch</h2><label>Branch name<input required maxLength={160} value={branchForm.name} onChange={(event) => setBranchForm({ ...branchForm, name: event.target.value })} /></label><label>Short code<input required maxLength={40} value={branchForm.code} onChange={(event) => setBranchForm({ ...branchForm, code: event.target.value })} /></label><label>IANA timezone<input required value={branchForm.timezone} onChange={(event) => setBranchForm({ ...branchForm, timezone: event.target.value })} /></label><button className="button button-primary" disabled={busy !== null} type="submit">{buttonText("branch", "Save branch")} <span>→</span></button></form>}
        {!step("branch_hours") && <form className="setup-card" onSubmit={submitHours}><p className="eyebrow">02 · HOURS</p><h2>Set a first opening</h2><p className="setup-card-copy">This saves Monday, 09:00–17:00 in the branch timezone. You can add more intervals later.</p><label>Branch<select required value={selectedBranch} onChange={(event) => setSelectedBranch(event.target.value)}>{branchOptions}</select></label><button className="button button-primary" disabled={busy !== null || !selectedBranch} type="submit">{buttonText("hours", "Save Monday hours")} <span>→</span></button></form>}
        {!step("doctor") && <form className="setup-card" onSubmit={submitDoctor}><p className="eyebrow">03 · CARE TEAM</p><h2>Add a doctor</h2><label>Public name<input required maxLength={160} value={doctorName} onChange={(event) => setDoctorName(event.target.value)} placeholder="Dr. Samira Khan" /></label><button className="button button-primary" disabled={busy !== null} type="submit">{buttonText("doctor", "Add doctor")} <span>→</span></button></form>}
        {!step("service") && <form className="setup-card" onSubmit={submitService}><p className="eyebrow">04 · SERVICE</p><h2>Create a service</h2><label>Service name<input required maxLength={160} value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder="General consultation" /></label><button className="button button-primary" disabled={busy !== null} type="submit">{buttonText("service", "Create service")} <span>→</span></button></form>}
        {!step("doctor_assignment") && <form className="setup-card" onSubmit={submitDoctorAssignment}><p className="eyebrow">05 · ASSIGN</p><h2>Place a doctor</h2><label>Branch<select required value={selectedBranch} onChange={(event) => setSelectedBranch(event.target.value)}>{branchOptions}</select></label><label>Doctor<select required value={selectedDoctor} onChange={(event) => setSelectedDoctor(event.target.value)}><option value="">Choose a doctor</option>{catalog.doctors.map((doctor) => <option key={doctor.id} value={doctor.id}>{doctor.public_name}</option>)}</select></label><button className="button button-primary" disabled={busy !== null || !selectedBranch || !selectedDoctor} type="submit">{buttonText("doctor-assignment", "Assign doctor")} <span>→</span></button></form>}
        {!step("service_assignment") && <form className="setup-card" onSubmit={submitServiceAssignment}><p className="eyebrow">06 · ASSIGN</p><h2>Place a service</h2><label>Branch<select required value={selectedBranch} onChange={(event) => setSelectedBranch(event.target.value)}>{branchOptions}</select></label><label>Service<select required value={selectedService} onChange={(event) => setSelectedService(event.target.value)}><option value="">Choose a service</option>{catalog.services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label><button className="button button-primary" disabled={busy !== null || !selectedBranch || !selectedService} type="submit">{buttonText("service-assignment", "Assign service")} <span>→</span></button></form>}
      </section>
      <div className="setup-actions">{setup.completed ? <p className="setup-success" role="status">Setup completed. Your workspace is ready.</p> : <button className="button button-primary" type="button" disabled={!setup.ready_to_complete || busy !== null} onClick={() => void completeSetup()}>{buttonText("complete", setup.ready_to_complete ? "Complete setup" : "Finish the steps above")}<span>→</span></button>}</div>
    </>}
  </div></main>;
}
