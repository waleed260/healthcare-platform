"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, apiPage, post, money, label, errorMessage } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import Pagination, { usePagination } from "../_lib/pagination";
import ProviderSelect from "./provider-select";

type Patient = { id: string; full_name: string; patient_number: string };
type Service = { id: string; name: string; price_minor: number; duration_minutes: number };
type Doctor = { id: string; public_name: string };
type Invoice = { id: string; patient_id: string; invoice_number: string; currency: string; subtotal_minor: number; discount_minor: number; tax_minor: number; total_minor: number; paid_minor: number; status: string; issued_at: string; notes: string | null; version: number };
type InvoiceDetail = Invoice & { patient_name: string; patient_number: string; void_reason: string | null; voided_at: string | null; refunded_minor: number; balance_minor: number; lines: InvoiceLine[]; payments: Payment[]; refunds: Refund[] };
type InvoiceLine = { id: string; service_id: string | null; provider_id: string | null; provider_name: string | null; description: string; quantity: number; unit_price_minor: number; tax_minor: number; line_total_minor: number };
type Payment = { id: string; amount_minor: number; currency: string; method: string; reference: string | null; paid_at: string };
type Refund = { id: string; amount_minor: number; currency: string; reason: string; method: string; reference: string | null; created_at: string };
type Session = { permissions?: string[] };
type LineInput = { description: string; quantity: number; unitPrice: string; taxMinor: number; serviceId: string; providerId: string };
type Appointment = { id: string; patient_id: string; service_id: string | null; doctor_id: string | null; status: string; starts_at: string };

const emptyLine = (): LineInput => ({ description: "", quantity: 1, unitPrice: "", taxMinor: 0, serviceId: "", providerId: "" });
const formatDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));

export default function BillingPage() {
  const searchParams = useSearchParams();
  const toast = useToast();
  const confirm = useConfirm();

  const [patients, setPatients] = useState<Patient[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Invoice form state
  const [showForm, setShowForm] = useState(false);
  const [patientId, setPatientId] = useState("");
  const [currency, setCurrency] = useState("PKR");
  const [discountMinor, setDiscountMinor] = useState(0);
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineInput[]>([emptyLine()]);
  const [formBusy, setFormBusy] = useState(false);

  // Detail drawer
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Payment form
  const [paymentFor, setPaymentFor] = useState<InvoiceDetail | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [paymentRef, setPaymentRef] = useState("");
  const [paymentBusy, setPaymentBusy] = useState(false);

  // Refund form
  const [refundFor, setRefundFor] = useState<InvoiceDetail | null>(null);
  const [refundAmount, setRefundAmount] = useState("");
  const [refundMethod, setRefundMethod] = useState("cash");
  const [refundReason, setRefundReason] = useState("");
  const [refundRef, setRefundRef] = useState("");
  const [refundBusy, setRefundBusy] = useState(false);

  const can = (p: string) => permissions.includes(p);
  const invoiceFetcher = useCallback(async (cursor: string | null, limit: number) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return apiPage<Invoice>(`/api/v1/invoices?${params.toString()}`);
  }, []);
  const { items: invoices, loading: pageLoading, hasMore, load: loadMore, reload, pageSize, changePageSize } = usePagination<Invoice>(invoiceFetcher);

  const loadMeta = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, patientRows] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Patient[]>("/api/v1/patients?limit=200"),
      ]);
      setPermissions(session.permissions ?? []);
      setPatients(patientRows ?? []);
      try {
        const svc = await api<Service[]>("/api/v1/services?limit=200");
        setServices(Array.isArray(svc) ? svc : []);
      } catch { setServices([]); }
    } catch (reason) {
      setError(errorMessage(reason, "Billing could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadMeta(); }, [loadMeta]);
  useEffect(() => { void reload(); }, [reload]);

  // Pre-fill from appointment query param
  useEffect(() => {
    const appointmentId = searchParams.get("from_appointment");
    if (!appointmentId) return;
    void (async () => {
      try {
        const appt = await api<Appointment>(`/api/v1/appointments/${appointmentId}`);
        if (appt.patient_id) setPatientId(appt.patient_id);
        const svc = services.find((s) => s.id === appt.service_id);
        if (svc) {
          setLines([{ description: svc.name, quantity: 1, unitPrice: (svc.price_minor / 100).toFixed(2), taxMinor: 0, serviceId: svc.id, providerId: appt.doctor_id ?? "" }]);
        }
        setShowForm(true);
      } catch { /* appointment might not be accessible */ }
    })();
  }, [searchParams, services]);

  const patientNames = new Map(patients.map((p) => [p.id, p.full_name]));

  // Line item helpers
  function updateLine(index: number, field: keyof LineInput, value: string | number) {
    setLines((prev) => prev.map((l, i) => i === index ? { ...l, [field]: value } : l));
  }
  function addLine() { setLines((prev) => [...prev, emptyLine()]); }
  function removeLine(index: number) { setLines((prev) => prev.length === 1 ? prev : prev.filter((_, i) => i !== index)); }
  function applyService(index: number, serviceId: string) {
    const svc = services.find((s) => s.id === serviceId);
    if (!svc) { updateLine(index, "serviceId", ""); return; }
    setLines((prev) => prev.map((l, i) => i === index ? { ...l, serviceId, description: svc.name, unitPrice: (svc.price_minor / 100).toFixed(2) } : l));
  }

  // Live totals
  const subtotal = lines.reduce((sum, l) => sum + Math.round(Number(l.unitPrice) * 100) * l.quantity + l.taxMinor, 0);
  const total = Math.max(subtotal - discountMinor, 0);

  async function createInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const apiLines = lines.map((l) => ({
      description: l.description.trim(),
      quantity: l.quantity,
      unit_price_minor: Math.round(Number(l.unitPrice) * 100),
      tax_minor: l.taxMinor,
      ...(l.serviceId ? { service_id: l.serviceId } : {}),
      ...(l.providerId ? { provider_id: l.providerId } : {}),
    }));
    if (apiLines.some((l) => !l.description || l.unit_price_minor <= 0)) {
      toast.error("Each line needs a description and positive price.");
      return;
    }
    setFormBusy(true);
    try {
      await post("/api/v1/invoices", {
        patient_id: patientId,
        currency: currency.toUpperCase(),
        discount_minor: discountMinor,
        notes: notes.trim() || null,
        lines: apiLines,
      });
      toast.success("Invoice issued.");
      setShowForm(false);
      setLines([emptyLine()]);
      setDiscountMinor(0);
      setNotes("");
      void reload();
    } catch (reason) {
      toast.error(errorMessage(reason, "The invoice could not be created."));
    } finally {
      setFormBusy(false);
    }
  }

  async function openDetail(invoiceId: string) {
    setDetailLoading(true);
    try {
      const data = await api<InvoiceDetail>(`/api/v1/invoices/${invoiceId}`);
      setDetail(data);
    } catch (reason) {
      toast.error(errorMessage(reason, "Invoice details could not be loaded."));
    } finally {
      setDetailLoading(false);
    }
  }

  async function voidInvoice(inv: InvoiceDetail) {
    const yes = await confirm({ message: `Void invoice ${inv.invoice_number}? This cannot be undone.`, title: "Void invoice", confirmLabel: "Void", danger: true });
    if (!yes) return;
    const reason = window.prompt("Reason for voiding this invoice:");
    if (!reason || reason.trim().length < 3) { toast.error("A reason of at least 3 characters is required."); return; }
    try {
      await post(`/api/v1/invoices/${inv.id}/void`, { reason: reason.trim(), expected_version: inv.version });
      toast.success("Invoice voided.");
      setDetail(null);
      void reload();
    } catch (reason_err) {
      toast.error(errorMessage(reason_err, "The invoice could not be voided."));
    }
  }

  async function recordPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!paymentFor) return;
    const amountMinor = Math.round(Number(paymentAmount) * 100);
    if (!Number.isFinite(amountMinor) || amountMinor <= 0) { toast.error("Enter a positive payment amount."); return; }
    setPaymentBusy(true);
    try {
      await post(`/api/v1/invoices/${paymentFor.id}/payments`, {
        amount_minor: amountMinor,
        method: paymentMethod,
        ...(paymentRef.trim() ? { reference: paymentRef.trim() } : {}),
      });
      toast.success("Payment recorded.");
      setPaymentFor(null);
      setPaymentAmount("");
      setPaymentRef("");
      void reload();
    } catch (reason) {
      toast.error(errorMessage(reason, "The payment could not be recorded."));
    } finally {
      setPaymentBusy(false);
    }
  }

  async function recordRefund(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!refundFor) return;
    const amountMinor = Math.round(Number(refundAmount) * 100);
    if (!Number.isFinite(amountMinor) || amountMinor <= 0) { toast.error("Enter a positive refund amount."); return; }
    if (refundReason.trim().length < 3) { toast.error("A reason of at least 3 characters is required."); return; }
    setRefundBusy(true);
    try {
      await post(`/api/v1/invoices/${refundFor.id}/refund`, {
        amount_minor: amountMinor,
        reason: refundReason.trim(),
        method: refundMethod,
        ...(refundRef.trim() ? { reference: refundRef.trim() } : {}),
      });
      toast.success("Refund processed.");
      setRefundFor(null);
      setRefundAmount("");
      setRefundReason("");
      setRefundRef("");
      void reload();
    } catch (reason) {
      toast.error(errorMessage(reason, "The refund could not be processed."));
    } finally {
      setRefundBusy(false);
    }
  }

  const outstanding = invoices.reduce((sum, inv) => sum + Math.max(inv.total_minor - inv.paid_minor, 0), 0);
  const openCount = invoices.filter((inv) => !["paid", "void", "refunded"].includes(inv.status)).length;

  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (pageLoading || invoices.length === 0 || !listRef.current) return;
    anime({
      targets: listRef.current.querySelectorAll(".invoice-row"),
      opacity: [0, 1],
      translateY: [20, 0],
      duration: 450,
      delay: anime.stagger(35, { start: 80 }),
      easing: "easeOutCubic",
    });
  }, [pageLoading, invoices.length]);

  return (
    <section className="dash-content billing-content" aria-busy={loading || pageLoading}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow">BUSINESS · CLEAR BALANCES</p>
          <h1>Make the numbers <em>legible.</em></h1>
        </div>
        <div className="header-actions">
          <button className="button button-secondary" type="button" onClick={() => void reload()} disabled={pageLoading}>Refresh <span>↻</span></button>
          {can("billing.manage") && <button className="button button-primary" type="button" onClick={() => setShowForm((v) => !v)}>{showForm ? "Close form" : "New invoice"} <span>＋</span></button>}
        </div>
      </div>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void loadMeta()}>Try again <span>→</span></button></div>}

      <div className="billing-summary">
        <div><span className="eyebrow">OUTSTANDING</span><strong>{money(outstanding, currency)}</strong></div>
        <div><span className="eyebrow">OPEN INVOICES</span><strong>{openCount}</strong></div>
        <div><span className="eyebrow">TOTAL SHOWN</span><strong>{invoices.length}</strong></div>
      </div>

      {/* Invoice builder */}
      {showForm && (
        <form className="surface-card invoice-builder" onSubmit={(e) => void createInvoice(e)}>
          <div className="surface-card-heading">
            <div><p className="eyebrow">NEW INVOICE</p><h2>Build the charge.</h2></div>
          </div>

          <div className="invoice-builder-meta">
            <label>Patient
              <select required value={patientId} onChange={(e) => setPatientId(e.target.value)}>
                <option value="">Choose patient</option>
                {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} · {p.patient_number}</option>)}
              </select>
            </label>
            <label>Currency
              <input required maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value)} />
            </label>
          </div>

          {/* Line items */}
          <div className="invoice-lines-header">
            <span className="line-desc-col">Description</span>
            <span className="line-qty-col">Qty</span>
            <span className="line-price-col">Unit price</span>
            <span className="line-tax-col">Tax</span>
            <span className="line-total-col">Line total</span>
            <span className="line-action-col"></span>
          </div>
          {lines.map((line, i) => {
            const lineTotal = Math.round(Number(line.unitPrice) * 100) * line.quantity + line.taxMinor;
            return (
              <div className="invoice-line-row" key={i}>
                <div className="line-desc-col">
                  {services.length > 0 && (
                    <select value={line.serviceId} onChange={(e) => applyService(i, e.target.value)}>
                      <option value="">Custom item</option>
                      {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  )}
                  <input required placeholder="Line description" value={line.description} onChange={(e) => updateLine(i, "description", e.target.value)} />
                </div>
                <input className="line-qty-col" type="number" min={1} required value={line.quantity} onChange={(e) => updateLine(i, "quantity", Math.max(1, parseInt(e.target.value) || 1))} />
                <input className="line-price-col" type="number" min="0.01" step="0.01" required placeholder="0.00" value={line.unitPrice} onChange={(e) => updateLine(i, "unitPrice", e.target.value)} />
                <input className="line-tax-col" type="number" min={0} value={line.taxMinor / 100} onChange={(e) => updateLine(i, "taxMinor", Math.round(Number(e.target.value) * 100))} placeholder="0" />
                <span className="line-total-col line-total-value">{money(lineTotal, currency)}</span>
                <button className="line-action-col ghost-button" type="button" onClick={() => removeLine(i)} disabled={lines.length === 1} aria-label="Remove line">×</button>
              </div>
            );
          })}
          <button className="button button-secondary invoice-add-line" type="button" onClick={addLine}>Add line <span>＋</span></button>

          <div className="invoice-totals">
            <div className="invoice-totals-row"><span>Subtotal</span><strong>{money(subtotal, currency)}</strong></div>
            <div className="invoice-totals-row">
              <label>Discount
                <input type="number" min={0} step="0.01" value={discountMinor / 100} onChange={(e) => setDiscountMinor(Math.round(Number(e.target.value) * 100))} />
              </label>
              <strong>−{money(discountMinor, currency)}</strong>
            </div>
            <div className="invoice-totals-row invoice-total-final"><span>Total</span><strong>{money(total, currency)}</strong></div>
          </div>

          <label className="invoice-notes-label">Notes <span className="field-optional">optional</span>
            <textarea rows={2} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Internal notes for this invoice" />
          </label>

          <div className="form-actions">
            <button className="button button-primary" type="submit" disabled={formBusy || !patientId}>{formBusy ? "Issuing…" : "Issue invoice"} <span>↗</span></button>
          </div>
        </form>
      )}

      {/* Invoice list */}
      <section className="surface-card invoice-card">
        <div className="surface-card-heading">
          <div><p className="eyebrow">INVOICE LEDGER</p><h2>Every balance, one place.</h2></div>
          <span className="muted-mono">{pageLoading ? "SYNCING" : `${invoices.length} RECORD${invoices.length === 1 ? "" : "S"}`}</span>
        </div>

        {pageLoading && invoices.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading billing</strong><span>Checking authorized invoices…</span></div>}
        {!pageLoading && invoices.length === 0 && <div className="dashboard-empty"><strong>No invoices yet</strong><span>Issue the first invoice when a service is ready to be charged.</span></div>}

        {invoices.length > 0 && (
          <div className="invoice-list" ref={listRef}>
            {invoices.map((inv) => {
              const balance = Math.max(inv.total_minor - inv.paid_minor, 0);
              return (
                <article className="invoice-row" key={inv.id}>
                  <div className="invoice-mark">{inv.invoice_number.slice(-2)}</div>
                  <div className="invoice-main">
                    <div className="lead-title">
                      <h3><button className="text-control" type="button" onClick={() => void openDetail(inv.id)}>{inv.invoice_number}</button></h3>
                      <span className={`pipeline-status status-${inv.status}`}>{label(inv.status)}</span>
                    </div>
                    <p>{patientNames.get(inv.patient_id) ?? "Patient"} · Issued {new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(inv.issued_at))}</p>
                    <small>{money(inv.paid_minor, inv.currency)} paid of {money(inv.total_minor, inv.currency)} · {money(balance, inv.currency)} remaining</small>
                  </div>
                  <div className="invoice-actions">
                    <span className="receipt-links">
                      <a className="text-control" href={`/api/v1/invoices/${inv.id}/receipt.pdf?format=a4`} target="_blank" rel="noreferrer">A4 PDF</a>
                      <a className="text-control" href={`/api/v1/invoices/${inv.id}/receipt.pdf?format=thermal`} target="_blank" rel="noreferrer">80 mm</a>
                    </span>
                    {balance > 0 && inv.status !== "void" && can("billing.manage") && (
                      <button className="text-control" type="button" onClick={() => void openDetail(inv.id).then(() => {})}>Pay / Refund <span>→</span></button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
        {(hasMore || invoices.length > 0) && <Pagination hasMore={hasMore} loading={pageLoading} total={invoices.length} onLoadMore={() => void loadMore()} pageSize={pageSize} onPageSizeChange={changePageSize} />}
      </section>

      {/* Invoice detail drawer */}
      {(detail || detailLoading) && (
        <div className="drawer-scrim" onClick={() => { setDetail(null); setPaymentFor(null); setRefundFor(null); }}>
          <div className="appointment-drawer invoice-detail-drawer" onClick={(e) => e.stopPropagation()}>
            <button className="drawer-close" type="button" onClick={() => { setDetail(null); setPaymentFor(null); setRefundFor(null); }} aria-label="Close">×</button>

            {detailLoading && <div className="dashboard-empty" role="status"><strong>Loading invoice…</strong></div>}
            {detail && (
              <>
                <p className="eyebrow">INVOICE DETAIL</p>
                <h2>{detail.invoice_number}</h2>
                <p className="drawer-note">{detail.patient_name} · {detail.patient_number}</p>
                <span className={`pipeline-status status-${detail.status}`}>{label(detail.status)}</span>

                {detail.void_reason && <p className="void-reason">Voided: {detail.void_reason}</p>}

                {/* Lines */}
                <div className="detail-section">
                  <p className="eyebrow">LINE ITEMS</p>
                  <div className="detail-lines">
                    {detail.lines.map((l) => (
                      <div className="detail-line-row" key={l.id}>
                        <span>{l.description}{l.provider_name ? ` · ${l.provider_name}` : ""}</span>
                        <span>{l.quantity} × {money(l.unit_price_minor, detail.currency)}</span>
                        <strong>{money(l.line_total_minor, detail.currency)}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="detail-totals">
                    <div><span>Subtotal</span><span>{money(detail.subtotal_minor, detail.currency)}</span></div>
                    {detail.discount_minor > 0 && <div><span>Discount</span><span>−{money(detail.discount_minor, detail.currency)}</span></div>}
                    {detail.tax_minor > 0 && <div><span>Tax</span><span>{money(detail.tax_minor, detail.currency)}</span></div>}
                    <div className="detail-total-final"><span>Total</span><strong>{money(detail.total_minor, detail.currency)}</strong></div>
                  </div>
                </div>

                {/* Payments */}
                <div className="detail-section">
                  <p className="eyebrow">PAYMENTS ({money(detail.paid_minor, detail.currency)} PAID)</p>
                  {detail.payments.length === 0 && <p className="muted-mono">No payments yet</p>}
                  {detail.payments.map((p) => (
                    <div className="detail-payment-row" key={p.id}>
                      <span>{label(p.method)}{p.reference ? ` · ${p.reference}` : ""}</span>
                      <span>{formatDate(p.paid_at)}</span>
                      <strong>{money(p.amount_minor, p.currency)}</strong>
                    </div>
                  ))}
                </div>

                {/* Refunds */}
                {detail.refunds.length > 0 && (
                  <div className="detail-section">
                    <p className="eyebrow">REFUNDS ({money(detail.refunded_minor, detail.currency)} REFUNDED)</p>
                    {detail.refunds.map((r) => (
                      <div className="detail-payment-row refund-row" key={r.id}>
                        <span>{r.reason} · {label(r.method)}</span>
                        <span>{formatDate(r.created_at)}</span>
                        <strong>−{money(r.amount_minor, r.currency)}</strong>
                      </div>
                    ))}
                  </div>
                )}

                {/* Action buttons */}
                {can("billing.manage") && detail.status !== "void" && (
                  <div className="detail-actions">
                    {detail.balance_minor > 0 && (
                      <button className="button button-primary" type="button" onClick={() => { setPaymentFor(detail); setPaymentAmount((detail.balance_minor / 100).toFixed(2)); }}>
                        Record payment <span>→</span>
                      </button>
                    )}
                    {detail.paid_minor > detail.refunded_minor && (
                      <button className="button button-secondary" type="button" onClick={() => { setRefundFor(detail); setRefundAmount(((detail.paid_minor - detail.refunded_minor) / 100).toFixed(2)); }}>
                        Issue refund <span>↩</span>
                      </button>
                    )}
                    <button className="button button-danger" type="button" onClick={() => void voidInvoice(detail)}>Void invoice</button>
                  </div>
                )}

                {detail.notes && <p className="invoice-notes">{detail.notes}</p>}
              </>
            )}
          </div>
        </div>
      )}

      {/* Payment drawer */}
      {paymentFor && (
        <div className="drawer-scrim" onClick={() => setPaymentFor(null)}>
          <form className="appointment-drawer payment-drawer" onClick={(e) => e.stopPropagation()} onSubmit={(e) => void recordPayment(e)}>
            <button className="drawer-close" type="button" onClick={() => setPaymentFor(null)} aria-label="Close">×</button>
            <p className="eyebrow">RECORD PAYMENT</p>
            <h2>{paymentFor.invoice_number}</h2>
            <p className="drawer-note">Outstanding: {money(paymentFor.balance_minor, paymentFor.currency)}</p>
            <label>Amount <input required min="0.01" step="0.01" type="number" value={paymentAmount} onChange={(e) => setPaymentAmount(e.target.value)} /></label>
            <label>Method
              <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}>
                <option value="cash">Cash</option><option value="card">Card</option><option value="bank_transfer">Bank transfer</option><option value="online">Online</option><option value="other">Other</option>
              </select>
            </label>
            <label>Reference <span className="field-optional">optional</span>
              <input maxLength={160} value={paymentRef} onChange={(e) => setPaymentRef(e.target.value)} placeholder="Transaction ID or note" />
            </label>
            <button className="button button-primary" type="submit" disabled={paymentBusy}>{paymentBusy ? "Recording…" : "Record payment"} <span>↗</span></button>
          </form>
        </div>
      )}

      {/* Refund drawer */}
      {refundFor && (
        <div className="drawer-scrim" onClick={() => setRefundFor(null)}>
          <form className="appointment-drawer refund-drawer" onClick={(e) => e.stopPropagation()} onSubmit={(e) => void recordRefund(e)}>
            <button className="drawer-close" type="button" onClick={() => setRefundFor(null)} aria-label="Close">×</button>
            <p className="eyebrow">ISSUE REFUND</p>
            <h2>{refundFor.invoice_number}</h2>
            <p className="drawer-note">Refundable: {money(refundFor.paid_minor - refundFor.refunded_minor, refundFor.currency)}</p>
            <label>Amount <input required min="0.01" step="0.01" type="number" value={refundAmount} onChange={(e) => setRefundAmount(e.target.value)} /></label>
            <label>Reason <input required minLength={3} maxLength={500} value={refundReason} onChange={(e) => setRefundReason(e.target.value)} placeholder="Why is this refund being issued?" /></label>
            <label>Method
              <select value={refundMethod} onChange={(e) => setRefundMethod(e.target.value)}>
                <option value="cash">Cash</option><option value="card">Card</option><option value="bank_transfer">Bank transfer</option><option value="online">Online</option><option value="other">Other</option>
              </select>
            </label>
            <label>Reference <span className="field-optional">optional</span>
              <input maxLength={160} value={refundRef} onChange={(e) => setRefundRef(e.target.value)} placeholder="Transaction ID or note" />
            </label>
            <button className="button button-primary" type="submit" disabled={refundBusy}>{refundBusy ? "Processing…" : "Issue refund"} <span>↩</span></button>
          </form>
        </div>
      )}
    </section>
  );
}
