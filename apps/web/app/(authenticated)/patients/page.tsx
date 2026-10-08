"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { apiPage, errorMessage } from "../_lib/client";
import Pagination, { usePagination } from "../_lib/pagination";
import AddPatientDrawer from "../_lib/add-patient-drawer";

type Patient = { id: string; patient_number: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; status: string; version: number };

const statuses = ["active", "inactive", "discharged", "deceased"];

export default function PatientsPage() {
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  const fetcher = useCallback(async (cursor: string | null, limit: number) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (activeSearch) params.set("search", activeSearch);
    if (statusFilter) params.set("status", statusFilter);
    if (cursor) params.set("cursor", cursor);
    return apiPage<Patient>(`/api/v1/patients?${params.toString()}`);
  }, [activeSearch, statusFilter]);

  const { items: patients, loading, hasMore, load, reload, pageSize, changePageSize } = usePagination(fetcher);

  useEffect(() => { void reload(); }, [reload]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActiveSearch(search.trim());
  }

  function onStatusChange(value: string) {
    setStatusFilter(value);
  }

  useEffect(() => { void reload(); }, [statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const patientListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (loading || patients.length === 0 || !patientListRef.current) return;
    anime({
      targets: patientListRef.current.querySelectorAll(".patient-row"),
      opacity: [0, 1],
      translateX: [-16, 0],
      duration: 420,
      delay: anime.stagger(30, { start: 80 }),
      easing: "easeOutCubic",
    });
  }, [loading, patients.length]);

  return (
    <section className="dash-content patient-content" aria-busy={loading}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow">CLINIC RECORDS · SCOPED ACCESS</p>
          <h1>People, <em>carefully.</em></h1>
        </div>
        <button className="button button-secondary" type="button" onClick={() => void reload()} disabled={loading}>Refresh <span>↻</span></button>
        <button className="button button-primary" type="button" onClick={() => setAddOpen(true)}>Add patient <span>+</span></button>
      </div>

      <div className="patient-toolbar">
        <form onSubmit={submit} role="search" aria-label="Search patients">
          <label htmlFor="patient-search">Search name, email, or phone</label>
          <div className="patient-search-row">
            <input id="patient-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Start typing a patient detail" />
            <button className="button button-primary" type="submit" disabled={loading}>Search <span>→</span></button>
          </div>
        </form>
        <div className="patient-filters">
          <label>
            Status
            <select value={statusFilter} onChange={(e) => onStatusChange(e.target.value)}>
              <option value="">All statuses</option>
              {statuses.map((s) => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </label>
        </div>
        <p className="privacy-caption">Only records in your authorized clinic scope appear here.</p>
      </div>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void reload()}>Try again <span>→</span></button></div>}

      <div className="patient-card">
        <div className="card-heading">
          <div>
            <p className="eyebrow">PATIENT DIRECTORY</p>
            <h2>{activeSearch ? `Results for "${activeSearch}"` : statusFilter ? `${statusFilter.charAt(0).toUpperCase() + statusFilter.slice(1)} patients` : "All active patients"}</h2>
          </div>
          <span className="directory-count">{loading && patients.length === 0 ? "…" : `${patients.length} shown`}</span>
        </div>

        {loading && patients.length === 0 && (
          <div className="dashboard-empty" role="status">
            <strong>Loading patient records</strong>
            <span>Checking your authorized clinic scope…</span>
          </div>
        )}

        {!loading && patients.length === 0 && (
          <div className="dashboard-empty">
            <strong>{activeSearch || statusFilter ? "No matching patients" : "No active patients yet"}</strong>
            <span>{activeSearch || statusFilter ? "Try a different search or filter." : <>Create your clinic foundation in <Link href="/onboarding">onboarding</Link>, or receive a public booking.</>}</span>
          </div>
        )}

        {patients.length > 0 && (
          <div className="patient-list" role="list" ref={patientListRef}>
            {patients.map((patient) => (
              <Link className="patient-row" href={`/patients/${patient.id}`} key={patient.id} role="listitem">
                <span className="patient-initial" aria-hidden="true">{patient.full_name.trim().charAt(0).toUpperCase()}</span>
                <span className="patient-main">
                  <strong>{patient.full_name}</strong>
                  <small>{patient.patient_number} · {patient.status}</small>
                </span>
                <span className="patient-contact">{patient.normalized_email ?? patient.normalized_phone ?? "No contact recorded"}</span>
                <span className="row-arrow" aria-hidden="true">→</span>
              </Link>
            ))}
          </div>
        )}

        <Pagination hasMore={hasMore} loading={loading} total={patients.length} onLoadMore={() => void load()} pageSize={pageSize} onPageSizeChange={changePageSize} />
      </div>

      <AddPatientDrawer open={addOpen} onClose={() => setAddOpen(false)} onCreated={() => void reload()} />
    </section>
  );
}
