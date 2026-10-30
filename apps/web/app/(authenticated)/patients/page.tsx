"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, apiPage, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import Pagination, { usePagination } from "../_lib/pagination";
import AddPatientDrawer from "../_lib/add-patient-drawer";
import DataTable, { type Column } from "../_lib/data-table";
import type { PatientSummary } from "../_lib/contracts";

const statuses = ["active", "inactive", "discharged", "deceased"];

const patientCols: Column<PatientSummary>[] = [
  { key: "initial", header: "", width: "34px", srOnly: true, render: (p) => <span className="patient-initial" aria-hidden="true">{p.full_name.trim().charAt(0).toUpperCase()}</span> },
  { key: "name", header: "Name", width: "1.3fr", sortable: true, sortFn: (a, b) => a.full_name.localeCompare(b.full_name), render: (p) => <span className="patient-main"><strong>{p.full_name}</strong><small>{p.patient_number} · {p.status}</small></span> },
  { key: "contact", header: "Contact", width: "1fr", render: (p) => <span className="patient-contact">{p.normalized_email ?? p.normalized_phone ?? "No contact"}</span> },
  { key: "arrow", header: "", width: "15px", srOnly: true, render: () => <span className="row-arrow" aria-hidden="true">→</span> },
];

export default function PatientsPage() {
  const toast = useToast();
  const confirm = useConfirm();
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const fetcher = useCallback(async (cursor: string | null, limit: number) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (activeSearch) params.set("search", activeSearch);
    if (statusFilter) params.set("status", statusFilter);
    if (cursor) params.set("cursor", cursor);
    return apiPage<PatientSummary>(`/api/v1/patients?${params.toString()}`);
  }, [activeSearch, statusFilter]);

  const { items: patients, loading, hasMore, error: paginationError, load, reload, pageSize, changePageSize } = usePagination(fetcher);

  const initialRef = useRef(true);
  useEffect(() => {
    if (initialRef.current) { initialRef.current = false; void reload(); return; }
    void reload();
  }, [activeSearch, statusFilter]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActiveSearch(search.trim());
  }

  async function bulkArchive() {
    const ok = await confirm({ message: `Archive ${selectedKeys.size} patient${selectedKeys.size === 1 ? "" : "s"}?`, danger: true });
    if (!ok) return;
    setBulkBusy(true);
    let done = 0;
    for (const id of selectedKeys) {
      try {
        await api(`/api/v1/patients/${id}/archive`, { method: "POST", headers: writeHeaders() });
        done++;
      } catch { /* continue */ }
    }
    setBulkBusy(false);
    setSelectedKeys(new Set());
    toast.success(`${done} patient${done === 1 ? "" : "s"} archived.`);
    void reload();
  }

  return (
    <main className="dash-content patient-content" aria-busy={loading}>
      <div className="dash-topline">
        <div>
          <h1>Patients</h1>
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
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              {statuses.map((s) => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </label>
        </div>
      </div>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void reload()}>Try again <span>→</span></button></div>}

      <div className="patient-card">
        <div className="card-heading">
          <div>
            <h2>{activeSearch ? `Results for "${activeSearch}"` : statusFilter ? `${statusFilter.charAt(0).toUpperCase() + statusFilter.slice(1)} patients` : "All patients"}</h2>
          </div>
          <span className="directory-count">{loading && patients.length === 0 ? "…" : `${patients.length} shown`}</span>
        </div>

        <DataTable
          columns={patientCols}
          rows={patients}
          rowKey={(p) => p.id}
          loading={loading && patients.length === 0}
          skeletonRows={6}
          selectable
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          emptyTitle={activeSearch || statusFilter ? "No matching patients" : "No patients yet"}
          emptyBody={activeSearch || statusFilter ? "Try a different search or filter." : <><Link href="/onboarding">Set up your clinic</Link>, or receive a public booking.</>}
          rowHref={(p) => `/patients/${p.id}`}
        />

        {selectedKeys.size > 0 && (
          <div className="bulk-bar">
            <strong>{selectedKeys.size} selected</strong>
            <button type="button" disabled={bulkBusy} onClick={() => void bulkArchive()}>{bulkBusy ? "Archiving…" : "Archive"}</button>
            <button type="button" onClick={() => setSelectedKeys(new Set())}>Clear</button>
          </div>
        )}

        <Pagination hasMore={hasMore} loading={loading} error={paginationError} total={patients.length} onLoadMore={() => void load()} pageSize={pageSize} onPageSizeChange={changePageSize} loadMoreLabel="Load more patients" />
      </div>

      <AddPatientDrawer open={addOpen} onClose={() => setAddOpen(false)} onCreated={() => void reload()} />
    </main>
  );
}
