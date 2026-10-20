"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, apiPage, errorMessage, label, money, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import Drawer from "../_lib/drawer";

/* ── types ──────────────────────────────────────────────────────────── */

type Product = { id: string; name: string; sku: string | null; product_type: string | null; unit: string; minimum_stock: string; status: string; version: number; category_id: string | null; cost_minor: number | null; selling_price_minor: number | null; currency: string | null; tax_inclusive: boolean };
type Stock = { id: string; branch_id: string; branch_name: string; product_id: string; product_name: string; product_type: string | null; unit: string; minimum_stock: string; category_id: string | null; quantity: string; low_stock: boolean; version: number };
type Branch = { id: string; name: string };
type Category = { id: string; name: string; slug: string; display_order: number };
type Session = { permissions?: string[]; user?: { id: string; display_name: string } };

type Supplier = { id: string; name: string; contact_name: string | null; email: string | null; phone: string | null; address: Record<string, string> | null; notes: string | null; status: string; version: number; created_at: string };
type Warehouse = { id: string; name: string; code: string; branch_id: string; branch_name: string; warehouse_type: string; contact_name: string | null; contact_phone: string | null; address: Record<string, string> | null; status: string; version: number; created_at: string };
type PurchaseOrder = { id: string; order_number: string; supplier_id: string; supplier_name: string; warehouse_id: string; warehouse_name: string; status: string; total_minor: number; currency: string; line_count: number; version: number; created_at: string };
type PurchaseOrderDetail = PurchaseOrder & { notes: string | null; ordered_by_name: string | null; ordered_at: string | null; received_at: string | null; lines: POLine[] };
type POLine = { id: string; product_id: string; product_name: string; quantity_ordered: string; quantity_received: string; unit_cost_minor: number };

type Transfer = { id: string; transfer_number: string; status: string; source_warehouse_id: string; source_warehouse_name: string; destination_warehouse_id: string; destination_warehouse_name: string; initiated_by_name: string; driver_name: string | null; line_count: number; version: number; created_at: string };
type TransferDetail = {
  id: string; transfer_number: string; status: string; notes: string | null; version: number; created_at: string; updated_at: string;
  source_warehouse_name: string; source_warehouse_code: string; source_branch_name: string;
  dest_warehouse_name: string; dest_warehouse_code: string; dest_branch_name: string;
  initiated_by_name: string; driver_name: string | null; driver_phone: string | null;
  handed_over_by_name: string | null; handed_over_at: string | null;
  received_by_name: string | null; received_at: string | null;
  cancelled_by_name: string | null; cancelled_at: string | null; cancel_reason: string | null;
  lines: TransferLine[];
};
type TransferLine = { id: string; product_id: string; product_name: string; sku: string | null; unit: string; quantity_sent: string; quantity_received: string | null; condition: string | null; checked_by_name: string | null; checked_at: string | null; notes: string | null };

const TABS = ["Stock", "Products", "Suppliers", "Purchases", "Warehouses", "Transfers"] as const;
type Tab = typeof TABS[number];

const UNIT_OPTIONS = ["Pieces", "mg", "ml", "g", "kg", "L", "Box", "Pack", "Tablet", "Capsule", "Vial", "Ampoule", "Tube"] as const;

const STATUS_MAP: Record<string, string> = { active: "paid", archived: "void", draft: "pending", ordered: "scheduled", partially_received: "pending", received: "paid", cancelled: "void", created: "pending", handover_for_transit: "scheduled" };

function StatusBadge({ status }: { status: string }) {
  return <span className={`pipeline-status status-${STATUS_MAP[status] ?? "pending"}`}>{label(status)}</span>;
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/* ── page ───────────────────────────────────────────────────────────── */

export default function InventoryPage() {
  const [tab, setTab] = useState<Tab>("Stock");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // shared
  const [products, setProducts] = useState<Product[]>([]);
  const [stock, setStock] = useState<Stock[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);

  // suppliers
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [showSupplierForm, setShowSupplierForm] = useState(false);
  const [sName, setSName] = useState(""); const [sContact, setSContact] = useState(""); const [sEmail, setSEmail] = useState(""); const [sPhone, setSPhone] = useState(""); const [sNotes, setSNotes] = useState("");

  // warehouses
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [showWarehouseForm, setShowWarehouseForm] = useState(false);
  const [wName, setWName] = useState(""); const [wCode, setWCode] = useState(""); const [wBranch, setWBranch] = useState(""); const [wType, setWType] = useState("warehouse"); const [wContactName, setWContactName] = useState(""); const [wContactPhone, setWContactPhone] = useState("");

  // purchases
  const [purchases, setPurchases] = useState<PurchaseOrder[]>([]);
  const [showPOForm, setShowPOForm] = useState(false);
  const [poSupplier, setPOSupplier] = useState(""); const [poWarehouse, setPOWarehouse] = useState(""); const [poNotes, setPONotes] = useState("");
  const [poLines, setPOLines] = useState<{ product_id: string; quantity_ordered: string; unit_cost_minor: string }[]>([{ product_id: "", quantity_ordered: "1", unit_cost_minor: "0" }]);
  const [poDetail, setPODetail] = useState<PurchaseOrderDetail | null>(null); const [showPODrawer, setShowPODrawer] = useState(false);
  const [poReceiveLines, setPOReceiveLines] = useState<{ line_id: string; quantity_received: string }[]>([]);

  // transfers
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [showTFForm, setShowTFForm] = useState(false);
  const [tfSource, setTFSource] = useState(""); const [tfDest, setTFDest] = useState(""); const [tfNotes, setTFNotes] = useState("");
  const [tfLines, setTFLines] = useState<{ product_id: string; quantity_sent: string }[]>([{ product_id: "", quantity_sent: "1" }]);
  const [tfDetail, setTFDetail] = useState<TransferDetail | null>(null); const [showTFDrawer, setShowTFDrawer] = useState(false);
  const [handoverName, setHandoverName] = useState(""); const [handoverPhone, setHandoverPhone] = useState("");
  const [receiveLines, setReceiveLines] = useState<{ line_id: string; quantity_received: string; condition: string; notes: string }[]>([]);
  const [tfStatusFilter, setTFStatusFilter] = useState("all");

  // existing state
  const [showProduct, setShowProduct] = useState(false);
  const [showAdjustment, setShowAdjustment] = useState(false);
  const [showCategory, setShowCategory] = useState(false);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [name, setName] = useState("");
  const [type, setType] = useState("consumable");
  const [sku, setSku] = useState("");
  const [minimum, setMinimum] = useState("0");
  const [unit, setUnit] = useState("Pieces");
  const [customUnit, setCustomUnit] = useState("");
  const [costMinor, setCostMinor] = useState("");
  const [sellingPrice, setSellingPrice] = useState("");
  const [taxInclusive, setTaxInclusive] = useState(false);
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [productId, setProductId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categorySlug, setCategorySlug] = useState("");

  const toast = useToast();
  const confirm = useConfirm();
  const can = (p: string) => permissions.includes(p);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    const [sessResult, productResult, stockResult, branchResult, categoryResult] = await Promise.allSettled([
      api<Session>("/api/v1/auth/me"),
      api<Product[]>("/api/v1/inventory/products?limit=100"),
      api<Stock[]>("/api/v1/inventory/stock"),
      api<Branch[]>("/api/v1/branches?limit=100"),
      api<Category[]>("/api/v1/inventory/categories"),
    ]);
    if (sessResult.status === "fulfilled") {
      setSession(sessResult.value); setPermissions(sessResult.value.permissions ?? []);
    }
    const productRows = productResult.status === "fulfilled" ? (productResult.value ?? []) : [];
    const stockRows = stockResult.status === "fulfilled" ? (stockResult.value ?? []) : [];
    const branchRows = branchResult.status === "fulfilled" ? (branchResult.value ?? []) : [];
    const categoryRows = categoryResult.status === "fulfilled" ? (categoryResult.value ?? []) : [];
    setProducts(productRows); setStock(stockRows); setBranches(branchRows); setCategories(categoryRows);
    if (!productId && productRows[0]) setProductId(productRows[0].id);
    if (!branchId && branchRows[0]) setBranchId(branchRows[0].id);
    const failed = [sessResult, productResult, stockResult, branchResult].filter((r) => r.status === "rejected");
    if (failed.length > 0) setError(errorMessage((failed[0] as PromiseRejectedResult).reason, "Some inventory data could not be loaded."));
    setLoading(false);
  }, [branchId, productId]);

  const loadSuppliers = useCallback(async () => {
    try { const page = await apiPage<Supplier>("/api/v1/suppliers?status=all&limit=100"); setSuppliers(page.data); } catch { /* ignore */ }
  }, []);
  const loadWarehouses = useCallback(async () => {
    try { const page = await apiPage<Warehouse>("/api/v1/warehouses?status=all&limit=100"); setWarehouses(page.data); } catch { /* ignore */ }
  }, []);
  const loadPurchases = useCallback(async () => {
    try { const page = await apiPage<PurchaseOrder>("/api/v1/purchases?limit=100"); setPurchases(page.data); } catch { /* ignore */ }
  }, []);
  const loadTransfers = useCallback(async () => {
    try {
      const url = tfStatusFilter === "all" ? "/api/v1/transfers?limit=100" : `/api/v1/transfers?status=${tfStatusFilter}&limit=100`;
      const page = await apiPage<Transfer>(url);
      setTransfers(page.data);
    } catch { /* ignore */ }
  }, [tfStatusFilter]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (tab === "Suppliers") void loadSuppliers(); }, [tab, loadSuppliers]);
  useEffect(() => { if (tab === "Warehouses" || tab === "Purchases" || tab === "Transfers") void loadWarehouses(); }, [tab, loadWarehouses]);
  useEffect(() => { if (tab === "Purchases") void loadPurchases(); }, [tab, loadPurchases]);
  useEffect(() => { if (tab === "Transfers") void loadTransfers(); }, [tab, loadTransfers]);

  /* ── stock helpers ──────────────────────────────────────────────── */

  const filteredStock = useMemo(() => {
    let result = stock;
    if (search) { const q = search.toLowerCase(); result = result.filter((s) => s.product_name.toLowerCase().includes(q) || s.branch_name.toLowerCase().includes(q)); }
    if (typeFilter !== "all") result = result.filter((s) => s.product_type === typeFilter);
    if (categoryFilter !== "all") result = result.filter((s) => s.category_id === categoryFilter);
    return result;
  }, [stock, search, typeFilter, categoryFilter]);

  const productTypes = useMemo(() => {
    const types = new Set(stock.map((s) => s.product_type).filter(Boolean));
    return Array.from(types).sort() as string[];
  }, [stock]);

  const categoryMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of categories) m.set(c.id, c.name);
    return m;
  }, [categories]);

  const lowCount = stock.filter((item) => item.low_stock).length;

  /* ── product actions ───────────────────────────────────────────── */

  async function createProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      const effectiveUnit = unit === "custom" ? customUnit : unit;
      await post("/api/v1/inventory/products", { name, sku: sku || null, product_type: type || null, unit: effectiveUnit, minimum_stock: minimum, category_id: selectedCategoryId || null, cost_minor: costMinor ? Math.round(Number(costMinor) * 100) : null, selling_price_minor: sellingPrice ? Math.round(Number(sellingPrice) * 100) : null, tax_inclusive: taxInclusive });
      setName(""); setSku(""); setMinimum("0"); setUnit("Pieces"); setCustomUnit(""); setCostMinor(""); setSellingPrice(""); setTaxInclusive(false); setSelectedCategoryId("");
      setShowProduct(false); toast.success("Product added."); await load();
    } catch (r) { toast.error(errorMessage(r, "The product could not be created.")); } finally { setBusy(false); }
  }

  async function adjustStock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      await post("/api/v1/inventory/adjustments", { product_id: productId, branch_id: branchId, delta, reason });
      setDelta(""); setReason(""); setShowAdjustment(false); toast.success("Stock adjusted."); await load();
    } catch (r) { toast.error(errorMessage(r, "The stock adjustment could not be saved.")); } finally { setBusy(false); }
  }

  async function toggleProductStatus(product: Product) {
    const newStatus = product.status === "active" ? "archived" : "active";
    const ok = await confirm({ message: `${newStatus === "archived" ? "Archive" : "Reactivate"} "${product.name}"?`, danger: newStatus === "archived" });
    if (!ok) return; setBusy(true);
    try {
      await api(`/api/v1/inventory/products/${product.id}/status`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ status: newStatus }) });
      toast.success(`Product ${newStatus === "archived" ? "archived" : "reactivated"}.`); await load();
    } catch (r) { toast.error(errorMessage(r, "The product status could not be changed.")); } finally { setBusy(false); }
  }

  async function createCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      await post("/api/v1/inventory/categories", { name: categoryName, slug: categorySlug });
      setCategoryName(""); setCategorySlug(""); setShowCategory(false); toast.success("Category created."); await load();
    } catch (r) { toast.error(errorMessage(r, "The category could not be created.")); } finally { setBusy(false); }
  }

  async function deleteCategory(id: string, categoryDisplayName: string) {
    const ok = await confirm({ message: `Delete category "${categoryDisplayName}"? Products in this category will become uncategorized.`, danger: true });
    if (!ok) return; setBusy(true);
    try {
      await api(`/api/v1/inventory/categories/${id}`, { method: "DELETE", headers: writeHeaders() });
      toast.success("Category deleted."); await load();
    } catch (r) { toast.error(errorMessage(r, "The category could not be deleted.")); } finally { setBusy(false); }
  }

  /* ── supplier actions ──────────────────────────────────────────── */

  async function createSupplier(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      await post("/api/v1/suppliers", { name: sName, contact_name: sContact || null, email: sEmail || null, phone: sPhone || null, notes: sNotes || null });
      setSName(""); setSContact(""); setSEmail(""); setSPhone(""); setSNotes("");
      setShowSupplierForm(false); toast.success("Supplier added."); await loadSuppliers();
    } catch (r) { toast.error(errorMessage(r, "Supplier could not be created.")); } finally { setBusy(false); }
  }

  async function toggleSupplierStatus(s: Supplier) {
    const newStatus = s.status === "active" ? "archived" : "active";
    const ok = await confirm({ message: `${newStatus === "archived" ? "Archive" : "Reactivate"} supplier "${s.name}"?`, danger: newStatus === "archived" });
    if (!ok) return; setBusy(true);
    try {
      await post(`/api/v1/suppliers/${s.id}/status`, { status: newStatus });
      toast.success(`Supplier ${newStatus === "archived" ? "archived" : "reactivated"}.`); await loadSuppliers();
    } catch (r) { toast.error(errorMessage(r, "Status could not be changed.")); } finally { setBusy(false); }
  }

  /* ── warehouse actions ─────────────────────────────────────────── */

  async function createWarehouse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      await post("/api/v1/warehouses", { name: wName, code: wCode, branch_id: wBranch, warehouse_type: wType, contact_name: wContactName || null, contact_phone: wContactPhone || null });
      setWName(""); setWCode(""); setWBranch(""); setWType("warehouse"); setWContactName(""); setWContactPhone("");
      setShowWarehouseForm(false); toast.success("Warehouse added."); await loadWarehouses();
    } catch (r) { toast.error(errorMessage(r, "Warehouse could not be created.")); } finally { setBusy(false); }
  }

  async function toggleWarehouseStatus(w: Warehouse) {
    const newStatus = w.status === "active" ? "archived" : "active";
    const ok = await confirm({ message: `${newStatus === "archived" ? "Archive" : "Reactivate"} warehouse "${w.name}"?`, danger: newStatus === "archived" });
    if (!ok) return; setBusy(true);
    try {
      await post(`/api/v1/warehouses/${w.id}/status`, { status: newStatus });
      toast.success(`Warehouse ${newStatus === "archived" ? "archived" : "reactivated"}.`); await loadWarehouses();
    } catch (r) { toast.error(errorMessage(r, "Status could not be changed.")); } finally { setBusy(false); }
  }

  /* ── purchase order actions ────────────────────────────────────── */

  async function createPO(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      const lines = poLines.filter((l) => l.product_id).map((l) => ({ product_id: l.product_id, quantity_ordered: l.quantity_ordered, unit_cost_minor: Math.round(Number(l.unit_cost_minor) * 100) }));
      await post("/api/v1/purchases", { supplier_id: poSupplier, warehouse_id: poWarehouse, notes: poNotes || null, lines });
      setPOSupplier(""); setPOWarehouse(""); setPONotes(""); setPOLines([{ product_id: "", quantity_ordered: "1", unit_cost_minor: "0" }]);
      setShowPOForm(false); toast.success("Purchase order created."); await loadPurchases();
    } catch (r) { toast.error(errorMessage(r, "Purchase order could not be created.")); } finally { setBusy(false); }
  }

  async function openPODetail(id: string) {
    try {
      const detail = await api<PurchaseOrderDetail>(`/api/v1/purchases/${id}`);
      setPODetail(detail);
      setPOReceiveLines(detail.lines.map((l) => ({ line_id: l.id, quantity_received: l.quantity_ordered })));
      setShowPODrawer(true);
    } catch (r) { toast.error(errorMessage(r, "Could not load purchase order.")); }
  }

  async function orderPO() {
    if (!poDetail) return; setBusy(true);
    try {
      await post(`/api/v1/purchases/${poDetail.id}/order`, { expected_version: poDetail.version });
      toast.success("Purchase order marked as ordered."); setShowPODrawer(false); await loadPurchases();
    } catch (r) { toast.error(errorMessage(r, "Could not mark as ordered.")); } finally { setBusy(false); }
  }

  async function receivePO() {
    if (!poDetail) return; setBusy(true);
    try {
      const lines = poReceiveLines.map((l) => ({ line_id: l.line_id, quantity_received: l.quantity_received }));
      await post(`/api/v1/purchases/${poDetail.id}/receive`, { expected_version: poDetail.version, lines });
      toast.success("Goods received and stock updated."); setShowPODrawer(false); await loadPurchases(); await load();
    } catch (r) { toast.error(errorMessage(r, "Could not receive goods.")); } finally { setBusy(false); }
  }

  async function cancelPO() {
    if (!poDetail) return;
    const ok = await confirm({ message: `Cancel purchase order ${poDetail.order_number}?`, danger: true });
    if (!ok) return; setBusy(true);
    try {
      await post(`/api/v1/purchases/${poDetail.id}/cancel`, { expected_version: poDetail.version });
      toast.success("Purchase order cancelled."); setShowPODrawer(false); await loadPurchases();
    } catch (r) { toast.error(errorMessage(r, "Could not cancel.")); } finally { setBusy(false); }
  }

  /* ── transfer actions ──────────────────────────────────────────── */

  async function createTransfer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      const lines = tfLines.filter((l) => l.product_id).map((l) => ({ product_id: l.product_id, quantity_sent: l.quantity_sent }));
      await post("/api/v1/transfers", { source_warehouse_id: tfSource, destination_warehouse_id: tfDest, notes: tfNotes || null, lines });
      setTFSource(""); setTFDest(""); setTFNotes(""); setTFLines([{ product_id: "", quantity_sent: "1" }]);
      setShowTFForm(false); toast.success("Transfer created."); await loadTransfers();
    } catch (r) { toast.error(errorMessage(r, "Transfer could not be created.")); } finally { setBusy(false); }
  }

  async function openTFDetail(id: string) {
    try {
      const detail = await api<TransferDetail>(`/api/v1/transfers/${id}`);
      setTFDetail(detail);
      setReceiveLines(detail.lines.map((l) => ({ line_id: l.id, quantity_received: l.quantity_sent, condition: "good", notes: "" })));
      setHandoverName(""); setHandoverPhone("");
      setShowTFDrawer(true);
    } catch (r) { toast.error(errorMessage(r, "Could not load transfer.")); }
  }

  async function handoverTransfer() {
    if (!tfDetail) return; setBusy(true);
    try {
      await post(`/api/v1/transfers/${tfDetail.id}/handover`, { expected_version: tfDetail.version, driver_name: handoverName, driver_phone: handoverPhone || null });
      toast.success("Transfer dispatched."); setShowTFDrawer(false); await loadTransfers();
    } catch (r) { toast.error(errorMessage(r, "Could not dispatch transfer.")); } finally { setBusy(false); }
  }

  async function receiveTransfer() {
    if (!tfDetail) return; setBusy(true);
    try {
      const lines = receiveLines.map((l) => ({ line_id: l.line_id, quantity_received: l.quantity_received, condition: l.condition, notes: l.notes || null }));
      await post(`/api/v1/transfers/${tfDetail.id}/receive`, { expected_version: tfDetail.version, lines });
      toast.success("Transfer received. Stock updated."); setShowTFDrawer(false); await loadTransfers(); await load();
    } catch (r) { toast.error(errorMessage(r, "Could not receive transfer.")); } finally { setBusy(false); }
  }

  async function cancelTransfer() {
    if (!tfDetail) return;
    const ok = await confirm({ message: `Cancel transfer ${tfDetail.transfer_number}?`, danger: true });
    if (!ok) return; setBusy(true);
    try {
      const reason = window.prompt("Cancellation reason:");
      if (!reason) { setBusy(false); return; }
      await post(`/api/v1/transfers/${tfDetail.id}/cancel`, { expected_version: tfDetail.version, reason });
      toast.success("Transfer cancelled."); setShowTFDrawer(false); await loadTransfers();
    } catch (r) { toast.error(errorMessage(r, "Could not cancel.")); } finally { setBusy(false); }
  }

  function printTransfer() {
    window.print();
  }

  /* ── active warehouses for dropdowns ───────────────────────────── */
  const activeWarehouses = useMemo(() => warehouses.filter((w) => w.status === "active"), [warehouses]);
  const activeSuppliers = useMemo(() => suppliers.filter((s) => s.status === "active"), [suppliers]);
  const activeProducts = useMemo(() => products.filter((p) => p.status === "active"), [products]);

  /* ── tab permission check ──────────────────────────────────────── */
  const canInventory = can("inventory.read") || can("inventory.manage");
  const canManage = can("inventory.manage");
  const tabVisible = (t: Tab): boolean => {
    switch (t) {
      case "Suppliers": return can("supplier.read") || can("supplier.manage") || canInventory;
      case "Purchases": return can("purchase.read") || can("purchase.manage") || canInventory;
      case "Warehouses": return can("warehouse.read") || can("warehouse.manage") || canInventory;
      case "Transfers": return can("transfer.read") || can("transfer.manage") || canInventory;
      default: return true;
    }
  };

  /* ── render ────────────────────────────────────────────────────── */

  return <main className="workspace-page inventory-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">OPERATIONS</p>
        <h1>Know what is <em>running low.</em></h1>
        <p className="workspace-page-intro">Products, suppliers, purchases, warehouses, and transfers.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => { void load(); if (tab === "Suppliers") void loadSuppliers(); if (tab === "Warehouses") void loadWarehouses(); if (tab === "Purchases") void loadPurchases(); if (tab === "Transfers") void loadTransfers(); }} disabled={loading}>Refresh <span>&#x21bb;</span></button>
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>&rarr;</span></button></div>}

    {/* Tab navigation */}
    <div className="pipeline-tabs" role="tablist" style={{ marginBottom: 20 }}>
      {TABS.filter(tabVisible).map((t) => <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}</button>)}
    </div>

    {/* ── STOCK TAB ─────────────────────────────────────────────── */}
    {tab === "Stock" && <>
      <div className="inventory-summary">
        <div className="inventory-summary-dark"><span className="eyebrow">LOW STOCK</span><strong>{lowCount}</strong><small>branch records need attention</small></div>
        <div><span className="eyebrow">PRODUCTS</span><strong>{products.length}</strong><small>active catalog items</small></div>
        <div><span className="eyebrow">BRANCH STOCK</span><strong>{stock.length}</strong><small>tracked locations</small></div>
      </div>

      {can("inventory.manage") && <div className="header-actions" style={{ marginBottom: 12, display: "flex", gap: 8 }}>
        <button className="button button-secondary" onClick={() => setShowCategory((v) => !v)}>Categories</button>
        <button className="button button-secondary" onClick={() => setShowAdjustment((v) => !v)}>Adjust stock</button>
      </div>}

      {showCategory && <section className="surface-card inventory-form">
        <div className="surface-card-heading"><div><p className="eyebrow">CATEGORIES</p><h2>Organize your inventory.</h2></div></div>
        {categories.length > 0 && <div className="invoice-list" style={{ marginBottom: 16 }}>
          {categories.map((c) => <article className="invoice-row" key={c.id}><div className="invoice-main"><h3>{c.name}</h3><p>{c.slug}</p></div><div className="invoice-actions"><button className="text-control" disabled={busy} onClick={() => void deleteCategory(c.id, c.name)}>Delete</button></div></article>)}
        </div>}
        <form onSubmit={createCategory} style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
          <label style={{ flex: 1, minWidth: 160 }}>Name<input required value={categoryName} onChange={(e) => setCategoryName(e.target.value)} placeholder="Instruments" /></label>
          <label style={{ flex: 1, minWidth: 160 }}>Slug<input required value={categorySlug} onChange={(e) => setCategorySlug(e.target.value)} placeholder="instruments" pattern="^[a-z0-9][a-z0-9-]*$" /></label>
          <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add category"}</button>
        </form>
      </section>}

      {showAdjustment && <form className="surface-card inventory-form" onSubmit={adjustStock}>
        <div className="surface-card-heading"><div><p className="eyebrow">STOCK ADJUSTMENT</p><h2>Leave a clear trail.</h2></div></div>
        <div className="form-grid">
          <label>Product<select required value={productId} onChange={(e) => setProductId(e.target.value)}><option value="">Choose product</option>{products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Branch<select required value={branchId} onChange={(e) => setBranchId(e.target.value)}><option value="">Choose branch</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Change quantity<input required type="number" step="0.001" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="+10 or -2" /></label>
          <label>Reason<input required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="New delivery / damaged stock" /></label>
        </div>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy || !productId || !branchId}>{busy ? "Saving…" : "Save adjustment"}</button></div>
      </form>}

      <section className="surface-card inventory-card">
        <div className="surface-card-heading"><div><p className="eyebrow">BRANCH STOCK</p><h2>What is on hand.</h2></div><span className="muted-mono">{loading ? "SYNCING" : `${filteredStock.length} RECORD${filteredStock.length === 1 ? "" : "S"}`}</span></div>
        {stock.length > 0 && <div className="pipeline-toolbar" style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input type="search" placeholder="Search products or branches…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 240, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />
            <div className="pipeline-tabs" role="tablist" style={{ fontSize: "0.78rem" }}>
              <button role="tab" aria-selected={typeFilter === "all"} className={typeFilter === "all" ? "active" : ""} onClick={() => setTypeFilter("all")}>All</button>
              {productTypes.map((t) => <button key={t} role="tab" aria-selected={typeFilter === t} className={typeFilter === t ? "active" : ""} onClick={() => setTypeFilter(t)}>{t}</button>)}
            </div>
            {categories.length > 0 && <div className="pipeline-tabs" role="tablist" style={{ fontSize: "0.78rem" }}>
              <button role="tab" aria-selected={categoryFilter === "all"} className={categoryFilter === "all" ? "active" : ""} onClick={() => setCategoryFilter("all")}>All categories</button>
              {categories.map((c) => <button key={c.id} role="tab" aria-selected={categoryFilter === c.id} className={categoryFilter === c.id ? "active" : ""} onClick={() => setCategoryFilter(c.id)}>{c.name}</button>)}
            </div>}
          </div>
        </div>}
        {loading && <div className="dashboard-empty" role="status"><strong>Loading stock</strong><span>Checking authorized branches…</span></div>}
        {!loading && filteredStock.length === 0 && <div className="dashboard-empty"><strong>{search || typeFilter !== "all" || categoryFilter !== "all" ? "No matching stock records" : "No stock records yet"}</strong><span>Add a product, then record its first branch adjustment.</span></div>}
        {!loading && filteredStock.length > 0 && <div className="inventory-list">
          {filteredStock.map((item) => <article className={`inventory-row ${item.low_stock ? "is-low" : ""}`} key={item.id}>
            <div className="inventory-mark">{item.low_stock ? "!" : "·"}</div>
            <div>
              <div className="inventory-title"><h3>{item.product_name}</h3>{item.low_stock && <span className="pipeline-status status-lost">LOW STOCK</span>}</div>
              <p>{item.branch_name} &middot; {item.product_type ?? "uncategorized"}{item.category_id && categoryMap.has(item.category_id) ? ` · ${categoryMap.get(item.category_id)}` : ""}</p>
              <small>{item.quantity} {item.unit} on hand &middot; minimum {item.minimum_stock} {item.unit}</small>
            </div>
            <span className="inventory-quantity">{item.quantity}<small>{item.unit}</small></span>
          </article>)}
        </div>}
      </section>
    </>}

    {/* ── PRODUCTS TAB ──────────────────────────────────────────── */}
    {tab === "Products" && <>
      {can("inventory.manage") && <div className="header-actions" style={{ marginBottom: 12 }}>
        <button className="button button-primary" onClick={() => setShowProduct((v) => !v)}>New product</button>
      </div>}

      {showProduct && <form className="surface-card inventory-form" onSubmit={createProduct}>
        <div className="surface-card-heading"><div><p className="eyebrow">NEW ITEM</p><h2>Add something the clinic relies on.</h2></div></div>
        <div className="form-grid">
          <label>Name<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Nitrile gloves" /></label>
          <label>SKU <span className="field-optional">optional</span><input value={sku} onChange={(e) => setSku(e.target.value)} placeholder="GLOVE-M" /></label>
          <label>Type<select value={type} onChange={(e) => setType(e.target.value)}><option value="product">Product</option><option value="medicine">Medicine</option><option value="consumable">Consumable</option><option value="material">Material</option></select></label>
          <label>Category <span className="field-optional">optional</span><select value={selectedCategoryId} onChange={(e) => setSelectedCategoryId(e.target.value)}><option value="">No category</option>{categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>Unit<select value={unit} onChange={(e) => setUnit(e.target.value)}>{UNIT_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}<option value="custom">Custom…</option></select></label>
          {unit === "custom" && <label>Custom unit<input required value={customUnit} onChange={(e) => setCustomUnit(e.target.value)} maxLength={40} placeholder="Enter unit name" /></label>}
          <label>Minimum stock<input type="number" min="0" step="0.001" value={minimum} onChange={(e) => setMinimum(e.target.value)} /></label>
          <label>Purchase price <span className="field-optional">optional</span><input type="number" min="0" step="0.01" value={costMinor} onChange={(e) => setCostMinor(e.target.value)} placeholder="0.00" /></label>
          <label>Selling price <span className="field-optional">optional</span><input type="number" min="0" step="0.01" value={sellingPrice} onChange={(e) => setSellingPrice(e.target.value)} placeholder="0.00" /></label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}><input type="checkbox" checked={taxInclusive} onChange={(e) => setTaxInclusive(e.target.checked)} style={{ width: "auto" }} /> Tax inclusive</label>
        </div>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add product"}</button></div>
      </form>}

      {products.length > 0 && <section className="surface-card">
        <div className="surface-card-heading"><div><p className="eyebrow">PRODUCT CATALOG</p><h2>All registered items.</h2></div></div>
        <div className="invoice-list">
          {products.map((item) => <article className="invoice-row" key={item.id}>
            <div className="invoice-mark">{(item.sku ?? item.name).slice(0, 3).toUpperCase()}</div>
            <div className="invoice-main">
              <h3>{item.name}</h3>
              <p>
                {item.product_type ?? "uncategorized"}
                {item.category_id && categoryMap.has(item.category_id) ? ` · ${categoryMap.get(item.category_id)}` : ""}
                {item.sku ? ` · SKU: ${item.sku}` : ""}
                {" · "}min: {item.minimum_stock} {item.unit}
                {item.selling_price_minor != null && ` · ${money(item.selling_price_minor, item.currency ?? "PKR")}`}
                {item.cost_minor != null && ` · cost ${money(item.cost_minor, item.currency ?? "PKR")}`}
                {item.tax_inclusive && " (incl. tax)"}
              </p>
            </div>
            <div className="invoice-actions">
              <StatusBadge status={item.status} />
              {can("inventory.manage") && <button className="text-control" disabled={busy} onClick={() => void toggleProductStatus(item)}>{item.status === "active" ? "Archive" : "Reactivate"}</button>}
            </div>
          </article>)}
        </div>
      </section>}
    </>}

    {/* ── SUPPLIERS TAB ─────────────────────────────────────────── */}
    {tab === "Suppliers" && <>
      {(can("supplier.manage") || canManage) && <div className="header-actions" style={{ marginBottom: 12 }}>
        <button className="button button-primary" onClick={() => setShowSupplierForm((v) => !v)}>New supplier</button>
      </div>}

      {showSupplierForm && <form className="surface-card inventory-form" onSubmit={createSupplier}>
        <div className="surface-card-heading"><div><p className="eyebrow">NEW SUPPLIER</p><h2>Add a vendor.</h2></div></div>
        <div className="form-grid">
          <label>Company name<input required value={sName} onChange={(e) => setSName(e.target.value)} placeholder="Pharma Distributors" /></label>
          <label>Contact person <span className="field-optional">optional</span><input value={sContact} onChange={(e) => setSContact(e.target.value)} placeholder="Ali Khan" /></label>
          <label>Email <span className="field-optional">optional</span><input type="email" value={sEmail} onChange={(e) => setSEmail(e.target.value)} placeholder="ali@pharma.com" /></label>
          <label>Phone <span className="field-optional">optional</span><input value={sPhone} onChange={(e) => setSPhone(e.target.value)} placeholder="03001234567" /></label>
          <label style={{ gridColumn: "1 / -1" }}>Notes <span className="field-optional">optional</span><input value={sNotes} onChange={(e) => setSNotes(e.target.value)} placeholder="Payment terms, delivery schedule, etc." /></label>
        </div>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add supplier"}</button></div>
      </form>}

      <section className="surface-card">
        <div className="surface-card-heading"><div><p className="eyebrow">SUPPLIERS</p><h2>Your vendor directory.</h2></div><span className="muted-mono">{suppliers.length} SUPPLIER{suppliers.length === 1 ? "" : "S"}</span></div>
        {suppliers.length === 0 && <div className="dashboard-empty"><strong>No suppliers yet</strong><span>Add your first vendor to start creating purchase orders.</span></div>}
        {suppliers.length > 0 && <div className="invoice-list">
          {suppliers.map((s) => <article className="invoice-row" key={s.id}>
            <div className="invoice-mark">{s.name.slice(0, 2).toUpperCase()}</div>
            <div className="invoice-main">
              <h3>{s.name}</h3>
              <p>{[s.contact_name, s.email, s.phone].filter(Boolean).join(" · ") || "No contact info"}</p>
            </div>
            <div className="invoice-actions">
              <StatusBadge status={s.status} />
              {(can("supplier.manage") || canManage) && <button className="text-control" disabled={busy} onClick={() => void toggleSupplierStatus(s)}>{s.status === "active" ? "Archive" : "Reactivate"}</button>}
            </div>
          </article>)}
        </div>}
      </section>
    </>}

    {/* ── PURCHASES TAB ─────────────────────────────────────────── */}
    {tab === "Purchases" && <>
      {(can("purchase.manage") || canManage) && <div className="header-actions" style={{ marginBottom: 12 }}>
        <button className="button button-primary" onClick={() => setShowPOForm((v) => !v)}>New purchase order</button>
      </div>}

      {showPOForm && <form className="surface-card inventory-form" onSubmit={createPO}>
        <div className="surface-card-heading"><div><p className="eyebrow">NEW PURCHASE ORDER</p><h2>Order from a supplier.</h2></div></div>
        <div className="form-grid">
          <label>Supplier<select required value={poSupplier} onChange={(e) => setPOSupplier(e.target.value)}><option value="">Choose supplier</option>{activeSuppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label>Receiving warehouse<select required value={poWarehouse} onChange={(e) => setPOWarehouse(e.target.value)}><option value="">Choose warehouse</option>{activeWarehouses.map((w) => <option key={w.id} value={w.id}>{w.name} ({w.code})</option>)}</select></label>
          <label style={{ gridColumn: "1 / -1" }}>Notes <span className="field-optional">optional</span><input value={poNotes} onChange={(e) => setPONotes(e.target.value)} /></label>
        </div>
        <div style={{ marginTop: 12 }}>
          <p className="eyebrow" style={{ marginBottom: 8 }}>LINE ITEMS</p>
          {poLines.map((line, i) => <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6, alignItems: "end", flexWrap: "wrap" }}>
            <label style={{ flex: 2, minWidth: 160 }}>Product<select required value={line.product_id} onChange={(e) => { const next = [...poLines]; next[i] = { ...next[i], product_id: e.target.value }; setPOLines(next); }}><option value="">Choose product</option>{activeProducts.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <label style={{ flex: 1, minWidth: 80 }}>Qty<input required type="number" min="0.001" step="0.001" value={line.quantity_ordered} onChange={(e) => { const next = [...poLines]; next[i] = { ...next[i], quantity_ordered: e.target.value }; setPOLines(next); }} /></label>
            <label style={{ flex: 1, minWidth: 80 }}>Unit cost<input required type="number" min="0" step="0.01" value={line.unit_cost_minor} onChange={(e) => { const next = [...poLines]; next[i] = { ...next[i], unit_cost_minor: e.target.value }; setPOLines(next); }} /></label>
            {poLines.length > 1 && <button type="button" className="text-control" onClick={() => setPOLines(poLines.filter((_, j) => j !== i))} style={{ marginBottom: 4 }}>&times;</button>}
          </div>)}
          <button type="button" className="button button-secondary" style={{ marginTop: 4 }} onClick={() => setPOLines([...poLines, { product_id: "", quantity_ordered: "1", unit_cost_minor: "0" }])}>Add line</button>
        </div>
        <div className="form-actions" style={{ marginTop: 12 }}><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Create purchase order"}</button></div>
      </form>}

      <section className="surface-card">
        <div className="surface-card-heading"><div><p className="eyebrow">PURCHASE ORDERS</p><h2>Incoming goods.</h2></div><span className="muted-mono">{purchases.length} ORDER{purchases.length === 1 ? "" : "S"}</span></div>
        {purchases.length === 0 && <div className="dashboard-empty"><strong>No purchase orders yet</strong><span>Create your first order to start receiving goods.</span></div>}
        {purchases.length > 0 && <div className="invoice-list">
          {purchases.map((po) => <article className="invoice-row" key={po.id} style={{ cursor: "pointer" }} onClick={() => void openPODetail(po.id)}>
            <div className="invoice-mark">{po.order_number}</div>
            <div className="invoice-main">
              <h3>{po.supplier_name}</h3>
              <p>{po.warehouse_name} &middot; {po.line_count} item{po.line_count === 1 ? "" : "s"} &middot; {money(po.total_minor, po.currency)}</p>
            </div>
            <div className="invoice-actions">
              <StatusBadge status={po.status} />
              <span className="muted-mono">{fmtDate(po.created_at)}</span>
            </div>
          </article>)}
        </div>}
      </section>

      {/* PO Drawer */}
      <Drawer open={showPODrawer} onClose={() => setShowPODrawer(false)} title={poDetail?.order_number ?? "Purchase Order"} subtitle="PURCHASE ORDER" width={560}>
        {poDetail && <>
          <div style={{ display: "grid", gap: 8, fontSize: "0.88rem", marginBottom: 16 }}>
            <div><strong>Supplier:</strong> {poDetail.supplier_name}</div>
            <div><strong>Warehouse:</strong> {poDetail.warehouse_name}</div>
            <div><strong>Status:</strong> <StatusBadge status={poDetail.status} /></div>
            <div><strong>Total:</strong> {money(poDetail.total_minor, poDetail.currency)}</div>
            {poDetail.notes && <div><strong>Notes:</strong> {poDetail.notes}</div>}
          </div>

          <table style={{ width: "100%", fontSize: "0.82rem", borderCollapse: "collapse" }}>
            <thead><tr style={{ borderBottom: "2px solid var(--border-subtle, #e5e5e3)" }}>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Product</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Ordered</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Received</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Unit cost</th>
            </tr></thead>
            <tbody>
              {poDetail.lines.map((l) => <tr key={l.id} style={{ borderBottom: "1px solid var(--border-subtle, #e5e5e3)" }}>
                <td style={{ padding: "6px 8px" }}>{l.product_name}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }}>{l.quantity_ordered}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }}>{l.quantity_received}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }}>{money(l.unit_cost_minor)}</td>
              </tr>)}
            </tbody>
          </table>

          {/* Receive form */}
          {(poDetail.status === "ordered" || poDetail.status === "partially_received") && (can("purchase.manage") || canManage) && <div style={{ marginTop: 20 }}>
            <p className="eyebrow" style={{ marginBottom: 8 }}>RECEIVE GOODS</p>
            {poReceiveLines.map((rl, i) => {
              const line = poDetail.lines.find((l) => l.id === rl.line_id);
              return <div key={rl.line_id} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, fontSize: "0.85rem" }}>
                <span style={{ flex: 2 }}>{line?.product_name}</span>
                <label style={{ flex: 1 }}>Qty received<input type="number" min="0" step="0.001" value={rl.quantity_received} onChange={(e) => { const next = [...poReceiveLines]; next[i] = { ...next[i], quantity_received: e.target.value }; setPOReceiveLines(next); }} /></label>
              </div>;
            })}
            <button className="button button-primary" disabled={busy} onClick={() => void receivePO()} style={{ marginTop: 8 }}>{busy ? "Receiving…" : "Receive goods"}</button>
          </div>}

          {/* Actions */}
          <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
            {poDetail.status === "draft" && (can("purchase.manage") || canManage) && <>
              <button className="button button-primary" disabled={busy} onClick={() => void orderPO()}>Mark ordered</button>
              <button className="button button-danger" disabled={busy} onClick={() => void cancelPO()}>Cancel</button>
            </>}
            {(poDetail.status === "ordered" || poDetail.status === "partially_received") && (can("purchase.manage") || canManage) && <button className="button button-danger" disabled={busy} onClick={() => void cancelPO()}>Cancel</button>}
          </div>
        </>}
      </Drawer>
    </>}

    {/* ── WAREHOUSES TAB ────────────────────────────────────────── */}
    {tab === "Warehouses" && <>
      {(can("warehouse.manage") || canManage) && <div className="header-actions" style={{ marginBottom: 12 }}>
        <button className="button button-primary" onClick={() => setShowWarehouseForm((v) => !v)}>New warehouse</button>
      </div>}

      {showWarehouseForm && <form className="surface-card inventory-form" onSubmit={createWarehouse}>
        <div className="surface-card-heading"><div><p className="eyebrow">NEW WAREHOUSE</p><h2>Add a storage location.</h2></div></div>
        <div className="form-grid">
          <label>Name<input required value={wName} onChange={(e) => setWName(e.target.value)} placeholder="Main Store" /></label>
          <label>Code<input required value={wCode} onChange={(e) => setWCode(e.target.value.toUpperCase())} placeholder="MAIN-01" pattern="^[A-Z0-9][A-Z0-9-]*$" /></label>
          <label>Branch<select required value={wBranch} onChange={(e) => setWBranch(e.target.value)}><option value="">Choose branch</option>{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label>Type<select value={wType} onChange={(e) => setWType(e.target.value)}><option value="warehouse">Warehouse</option><option value="store">Store</option><option value="cold_storage">Cold Storage</option></select></label>
          <label>Contact name <span className="field-optional">optional</span><input value={wContactName} onChange={(e) => setWContactName(e.target.value)} /></label>
          <label>Contact phone <span className="field-optional">optional</span><input value={wContactPhone} onChange={(e) => setWContactPhone(e.target.value)} /></label>
        </div>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add warehouse"}</button></div>
      </form>}

      <section className="surface-card">
        <div className="surface-card-heading"><div><p className="eyebrow">WAREHOUSES</p><h2>Storage locations.</h2></div><span className="muted-mono">{warehouses.length} LOCATION{warehouses.length === 1 ? "" : "S"}</span></div>
        {warehouses.length === 0 && <div className="dashboard-empty"><strong>No warehouses yet</strong><span>Add your first storage location linked to a branch.</span></div>}
        {warehouses.length > 0 && <div className="invoice-list">
          {warehouses.map((w) => <article className="invoice-row" key={w.id}>
            <div className="invoice-mark">{w.code.slice(0, 3)}</div>
            <div className="invoice-main">
              <h3>{w.name} <small style={{ fontWeight: 400, opacity: 0.7 }}>({w.code})</small></h3>
              <p>{w.branch_name} &middot; {label(w.warehouse_type)}{w.contact_name ? ` · ${w.contact_name}` : ""}</p>
            </div>
            <div className="invoice-actions">
              <StatusBadge status={w.status} />
              {(can("warehouse.manage") || canManage) && <button className="text-control" disabled={busy} onClick={() => void toggleWarehouseStatus(w)}>{w.status === "active" ? "Archive" : "Reactivate"}</button>}
            </div>
          </article>)}
        </div>}
      </section>
    </>}

    {/* ── TRANSFERS TAB ─────────────────────────────────────────── */}
    {tab === "Transfers" && <>
      <div className="header-actions" style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {(can("transfer.manage") || canManage) && <button className="button button-primary" onClick={() => setShowTFForm((v) => !v)}>New transfer</button>}
        <div className="pipeline-tabs" role="tablist" style={{ fontSize: "0.78rem" }}>
          {["all", "created", "handover_for_transit", "received", "cancelled"].map((s) => <button key={s} role="tab" aria-selected={tfStatusFilter === s} className={tfStatusFilter === s ? "active" : ""} onClick={() => setTFStatusFilter(s)}>{s === "all" ? "All" : label(s)}</button>)}
        </div>
      </div>

      {showTFForm && <form className="surface-card inventory-form" onSubmit={createTransfer}>
        <div className="surface-card-heading"><div><p className="eyebrow">NEW TRANSFER</p><h2>Move stock between warehouses.</h2></div></div>
        <div className="form-grid">
          <label>Source warehouse<select required value={tfSource} onChange={(e) => setTFSource(e.target.value)}><option value="">Choose source</option>{activeWarehouses.map((w) => <option key={w.id} value={w.id}>{w.name} ({w.code})</option>)}</select></label>
          <label>Destination warehouse<select required value={tfDest} onChange={(e) => setTFDest(e.target.value)}><option value="">Choose destination</option>{activeWarehouses.filter((w) => w.id !== tfSource).map((w) => <option key={w.id} value={w.id}>{w.name} ({w.code})</option>)}</select></label>
          <label style={{ gridColumn: "1 / -1" }}>Notes <span className="field-optional">optional</span><input value={tfNotes} onChange={(e) => setTFNotes(e.target.value)} /></label>
        </div>
        <div style={{ marginTop: 12 }}>
          <p className="eyebrow" style={{ marginBottom: 8 }}>ITEMS TO TRANSFER</p>
          {tfLines.map((line, i) => <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6, alignItems: "end", flexWrap: "wrap" }}>
            <label style={{ flex: 2, minWidth: 160 }}>Product<select required value={line.product_id} onChange={(e) => { const next = [...tfLines]; next[i] = { ...next[i], product_id: e.target.value }; setTFLines(next); }}><option value="">Choose product</option>{activeProducts.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <label style={{ flex: 1, minWidth: 80 }}>Qty<input required type="number" min="0.001" step="0.001" value={line.quantity_sent} onChange={(e) => { const next = [...tfLines]; next[i] = { ...next[i], quantity_sent: e.target.value }; setTFLines(next); }} /></label>
            {tfLines.length > 1 && <button type="button" className="text-control" onClick={() => setTFLines(tfLines.filter((_, j) => j !== i))} style={{ marginBottom: 4 }}>&times;</button>}
          </div>)}
          <button type="button" className="button button-secondary" style={{ marginTop: 4 }} onClick={() => setTFLines([...tfLines, { product_id: "", quantity_sent: "1" }])}>Add line</button>
        </div>
        <div className="form-actions" style={{ marginTop: 12 }}><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Creating…" : "Create transfer"}</button></div>
      </form>}

      <section className="surface-card">
        <div className="surface-card-heading"><div><p className="eyebrow">TRANSFERS</p><h2>Inter-warehouse movements.</h2></div><span className="muted-mono">{transfers.length} TRANSFER{transfers.length === 1 ? "" : "S"}</span></div>
        {transfers.length === 0 && <div className="dashboard-empty"><strong>No transfers yet</strong><span>Create a transfer to move stock between warehouses.</span></div>}
        {transfers.length > 0 && <div className="invoice-list">
          {transfers.map((tf) => <article className="invoice-row" key={tf.id} style={{ cursor: "pointer" }} onClick={() => void openTFDetail(tf.id)}>
            <div className="invoice-mark">{tf.transfer_number}</div>
            <div className="invoice-main">
              <h3>{tf.source_warehouse_name} &rarr; {tf.destination_warehouse_name}</h3>
              <p>{tf.initiated_by_name} &middot; {tf.line_count} item{tf.line_count === 1 ? "" : "s"}{tf.driver_name ? ` · Driver: ${tf.driver_name}` : ""}</p>
            </div>
            <div className="invoice-actions">
              <StatusBadge status={tf.status} />
              <span className="muted-mono">{fmtDate(tf.created_at)}</span>
            </div>
          </article>)}
        </div>}
      </section>

      {/* Transfer Detail Drawer */}
      <Drawer open={showTFDrawer} onClose={() => setShowTFDrawer(false)} title={tfDetail?.transfer_number ?? "Transfer"} subtitle="INVENTORY TRANSFER" width={640}>
        {tfDetail && <div className="transfer-detail-print">
          {/* Status timeline */}
          <div style={{ display: "grid", gap: 8, fontSize: "0.88rem", marginBottom: 16 }}>
            <div><strong>Status:</strong> <StatusBadge status={tfDetail.status} /></div>
            <div><strong>From:</strong> {tfDetail.source_warehouse_name} ({tfDetail.source_warehouse_code}) &mdash; {tfDetail.source_branch_name}</div>
            <div><strong>To:</strong> {tfDetail.dest_warehouse_name} ({tfDetail.dest_warehouse_code}) &mdash; {tfDetail.dest_branch_name}</div>
            <div><strong>Initiated by:</strong> {tfDetail.initiated_by_name} on {fmtDate(tfDetail.created_at)}</div>
            {tfDetail.notes && <div><strong>Notes:</strong> {tfDetail.notes}</div>}
            {tfDetail.handed_over_by_name && <div><strong>Dispatched by:</strong> {tfDetail.handed_over_by_name} on {fmtDate(tfDetail.handed_over_at)} &middot; Driver: {tfDetail.driver_name}{tfDetail.driver_phone ? ` (${tfDetail.driver_phone})` : ""}</div>}
            {tfDetail.received_by_name && <div><strong>Received by:</strong> {tfDetail.received_by_name} on {fmtDate(tfDetail.received_at)}</div>}
            {tfDetail.cancelled_by_name && <div><strong>Cancelled by:</strong> {tfDetail.cancelled_by_name} on {fmtDate(tfDetail.cancelled_at)} &mdash; {tfDetail.cancel_reason}</div>}
          </div>

          {/* Lines table */}
          <table style={{ width: "100%", fontSize: "0.82rem", borderCollapse: "collapse" }}>
            <thead><tr style={{ borderBottom: "2px solid var(--border-subtle, #e5e5e3)" }}>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Product</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>SKU</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Sent</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Received</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Condition</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Checked by</th>
            </tr></thead>
            <tbody>
              {tfDetail.lines.map((l) => <tr key={l.id} style={{ borderBottom: "1px solid var(--border-subtle, #e5e5e3)" }}>
                <td style={{ padding: "6px 8px" }}>{l.product_name}</td>
                <td style={{ padding: "6px 8px" }}>{l.sku ?? "—"}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }}>{l.quantity_sent} {l.unit}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }}>{l.quantity_received ?? "—"}</td>
                <td style={{ padding: "6px 8px" }}>{l.condition ? label(l.condition) : "—"}</td>
                <td style={{ padding: "6px 8px" }}>{l.checked_by_name ? `${l.checked_by_name} (${fmtDate(l.checked_at)})` : "—"}</td>
              </tr>)}
            </tbody>
          </table>

          {/* Print signature section */}
          <div className="print-only" style={{ marginTop: 32 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 24 }}>
              <div><div style={{ borderBottom: "1px solid #000", height: 32 }} /><small>Prepared by (sign)</small></div>
              <div><div style={{ borderBottom: "1px solid #000", height: 32 }} /><small>Dispatched by (sign)</small></div>
              <div><div style={{ borderBottom: "1px solid #000", height: 32 }} /><small>Driver / Rider (sign)</small></div>
              <div><div style={{ borderBottom: "1px solid #000", height: 32 }} /><small>Received by (sign)</small></div>
            </div>
            <p style={{ marginTop: 16, fontSize: "0.75rem", opacity: 0.6 }}>Printed by {session?.user?.display_name ?? "—"} on {new Date().toLocaleString()}</p>
          </div>

          {/* CREATED: Handover form */}
          {tfDetail.status === "created" && (can("transfer.manage") || canManage) && <div className="no-print" style={{ marginTop: 20 }}>
            <p className="eyebrow" style={{ marginBottom: 8 }}>HANDOVER TO DRIVER</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }}>
              <label style={{ flex: 1, minWidth: 140 }}>Driver name<input required value={handoverName} onChange={(e) => setHandoverName(e.target.value)} placeholder="Rider name" /></label>
              <label style={{ flex: 1, minWidth: 140 }}>Driver phone <span className="field-optional">optional</span><input value={handoverPhone} onChange={(e) => setHandoverPhone(e.target.value)} /></label>
              <button className="button button-primary" disabled={busy || !handoverName} onClick={() => void handoverTransfer()}>{busy ? "Dispatching…" : "Dispatch"}</button>
            </div>
          </div>}

          {/* HANDOVER_FOR_TRANSIT: Receiving checklist */}
          {tfDetail.status === "handover_for_transit" && (can("transfer.manage") || canManage) && <div className="no-print" style={{ marginTop: 20 }}>
            <p className="eyebrow" style={{ marginBottom: 8 }}>RECEIVING CHECKLIST</p>
            {receiveLines.map((rl, i) => {
              const line = tfDetail.lines.find((l) => l.id === rl.line_id);
              return <div key={rl.line_id} style={{ display: "flex", gap: 8, alignItems: "end", marginBottom: 8, flexWrap: "wrap", fontSize: "0.85rem", padding: 8, background: "var(--surface-1, #fafaf8)", borderRadius: 6 }}>
                <span style={{ flex: 2, minWidth: 120, fontWeight: 500 }}>{line?.product_name} <small style={{ fontWeight: 400 }}>({line?.quantity_sent} {line?.unit} sent)</small></span>
                <label style={{ flex: 1, minWidth: 80 }}>Qty received<input type="number" min="0" step="0.001" value={rl.quantity_received} onChange={(e) => { const next = [...receiveLines]; next[i] = { ...next[i], quantity_received: e.target.value }; setReceiveLines(next); }} /></label>
                <label style={{ flex: 1, minWidth: 90 }}>Condition<select value={rl.condition} onChange={(e) => { const next = [...receiveLines]; next[i] = { ...next[i], condition: e.target.value }; setReceiveLines(next); }}><option value="good">Good</option><option value="damaged">Damaged</option><option value="short">Short</option></select></label>
                <label style={{ flex: 1, minWidth: 100 }}>Notes<input value={rl.notes} onChange={(e) => { const next = [...receiveLines]; next[i] = { ...next[i], notes: e.target.value }; setReceiveLines(next); }} placeholder="Optional" /></label>
              </div>;
            })}
            <button className="button button-primary" disabled={busy} onClick={() => void receiveTransfer()} style={{ marginTop: 8 }}>{busy ? "Receiving…" : "Confirm received"}</button>
          </div>}

          {/* Cancel + Print */}
          <div className="no-print" style={{ marginTop: 16, display: "flex", gap: 8 }}>
            <button className="button button-secondary" onClick={printTransfer}>Print form</button>
            {tfDetail.status !== "received" && tfDetail.status !== "cancelled" && (can("transfer.manage") || canManage) && <button className="button button-danger" disabled={busy} onClick={() => void cancelTransfer()}>Cancel transfer</button>}
          </div>
        </div>}
      </Drawer>

      {/* Print CSS */}
      <style>{`
        @media print {
          body > *:not(.drawer-scrim) { display: none !important; }
          .drawer-scrim { position: static !important; background: none !important; }
          .drawer-panel { position: static !important; width: 100% !important; box-shadow: none !important; overflow: visible !important; }
          .drawer-close, .no-print { display: none !important; }
          .print-only { display: block !important; }
        }
        @media screen { .print-only { display: none; } }
      `}</style>
    </>}
  </main>;
}
