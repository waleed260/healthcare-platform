"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type Product = { id: string; name: string; sku: string | null; product_type: string; unit: string; minimum_stock: string; status: string; version: number };
type Stock = { id: string; branch_id: string; branch_name: string; product_id: string; product_name: string; product_type: string; unit: string; minimum_stock: string; quantity: string; low_stock: boolean; version: number };
type Branch = { id: string; name: string };
type Session = { permissions?: string[] };

export default function InventoryPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [stock, setStock] = useState<Stock[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showProduct, setShowProduct] = useState(false);
  const [showAdjustment, setShowAdjustment] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");

  const [name, setName] = useState("");
  const [type, setType] = useState("consumable");
  const [sku, setSku] = useState("");
  const [minimum, setMinimum] = useState("0");
  const [productId, setProductId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");

  const toast = useToast();
  const confirm = useConfirm();
  const can = (permission: string) => permissions.includes(permission);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, productRows, stockRows, branchRows] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Product[]>("/api/v1/inventory/products?limit=100"),
        api<Stock[]>("/api/v1/inventory/stock"),
        api<Branch[]>("/api/v1/branches?limit=100"),
      ]);
      setPermissions(session.permissions ?? []);
      setProducts(productRows ?? []);
      setStock(stockRows ?? []);
      setBranches(branchRows ?? []);
      if (!productId && productRows?.[0]) setProductId(productRows[0].id);
      if (!branchId && branchRows?.[0]) setBranchId(branchRows[0].id);
    } catch (reasonValue) {
      setError(errorMessage(reasonValue, "Inventory could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [branchId, productId]);
  useEffect(() => { void load(); }, [load]);

  const filteredStock = useMemo(() => {
    let result = stock;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((s) => s.product_name.toLowerCase().includes(q) || s.branch_name.toLowerCase().includes(q));
    }
    if (typeFilter !== "all") {
      result = result.filter((s) => s.product_type === typeFilter);
    }
    return result;
  }, [stock, search, typeFilter]);

  const productTypes = useMemo(() => {
    const types = new Set(stock.map((s) => s.product_type));
    return Array.from(types).sort();
  }, [stock]);

  async function createProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await post("/api/v1/inventory/products", { name, sku: sku || null, product_type: type, unit: "unit", minimum_stock: minimum });
      setName(""); setSku(""); setMinimum("0"); setShowProduct(false);
      toast.success("Product added.");
      await load();
    } catch (reasonValue) {
      toast.error(errorMessage(reasonValue, "The product could not be created."));
    } finally {
      setBusy(false);
    }
  }

  async function adjustStock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await post("/api/v1/inventory/adjustments", { product_id: productId, branch_id: branchId, delta, reason });
      setDelta(""); setReason(""); setShowAdjustment(false);
      toast.success("Stock adjusted.");
      await load();
    } catch (reasonValue) {
      toast.error(errorMessage(reasonValue, "The stock adjustment could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function toggleProductStatus(product: Product) {
    const newStatus = product.status === "active" ? "archived" : "active";
    const ok = await confirm({ message: `${newStatus === "archived" ? "Archive" : "Reactivate"} "${product.name}"?`, danger: newStatus === "archived" });
    if (!ok) return;
    setBusy(true);
    try {
      await api(`/api/v1/inventory/products/${product.id}/status`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ status: newStatus }) });
      toast.success(`Product ${newStatus === "archived" ? "archived" : "reactivated"}.`);
      await load();
    } catch (reasonValue) {
      toast.error(errorMessage(reasonValue, "The product status could not be changed."));
    } finally {
      setBusy(false);
    }
  }

  const lowCount = stock.filter((item) => item.low_stock).length;

  const invRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !invRef.current) return;
    anime({ targets: invRef.current.querySelectorAll(".surface-card, .invoice-row, .inventory-summary > div"), opacity: [0, 1], translateY: [20, 0], duration: 480, delay: anime.stagger(40, { start: 100 }), easing: "easeOutCubic" });
  }, [loading]);

  return <main className="workspace-page inventory-page" ref={invRef}>
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">OPERATIONS</p>
        <h1>Know what is <em>running low.</em></h1>
        <p className="workspace-page-intro">Products, medicines, consumables, and materials by branch, with every adjustment explained.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        {can("inventory.manage") && <>
          <button className="button button-secondary" onClick={() => setShowAdjustment((v) => !v)}>Adjust stock <span>＋</span></button>
          <button className="button button-primary" onClick={() => setShowProduct((v) => !v)}>New product <span>＋</span></button>
        </>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="inventory-summary">
      <div className="inventory-summary-dark"><span className="eyebrow">LOW STOCK</span><strong>{lowCount}</strong><small>branch records need attention</small></div>
      <div><span className="eyebrow">PRODUCTS</span><strong>{products.length}</strong><small>active catalog items</small></div>
      <div><span className="eyebrow">BRANCH STOCK</span><strong>{stock.length}</strong><small>tracked locations</small></div>
    </div>

    {showProduct && <form className="surface-card inventory-form" onSubmit={createProduct}>
      <div className="surface-card-heading"><div><p className="eyebrow">NEW ITEM</p><h2>Add something the clinic relies on.</h2></div></div>
      <div className="form-grid">
        <label>Name<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Nitrile gloves" /></label>
        <label>SKU <span className="field-optional">optional</span><input value={sku} onChange={(e) => setSku(e.target.value)} placeholder="GLOVE-M" /></label>
        <label>Type<select value={type} onChange={(e) => setType(e.target.value)}><option value="product">Product</option><option value="medicine">Medicine</option><option value="consumable">Consumable</option><option value="material">Material</option></select></label>
        <label>Minimum stock<input type="number" min="0" step="0.001" value={minimum} onChange={(e) => setMinimum(e.target.value)} /></label>
      </div>
      <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add product"}<span>↗</span></button></div>
    </form>}

    {showAdjustment && <form className="surface-card inventory-form" onSubmit={adjustStock}>
      <div className="surface-card-heading"><div><p className="eyebrow">STOCK ADJUSTMENT</p><h2>Leave a clear trail.</h2></div></div>
      <div className="form-grid">
        <label>Product<select required value={productId} onChange={(e) => setProductId(e.target.value)}><option value="">Choose product</option>{products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Branch<select required value={branchId} onChange={(e) => setBranchId(e.target.value)}><option value="">Choose branch</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Change quantity<input required type="number" step="0.001" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="+10 or -2" /></label>
        <label>Reason<input required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="New delivery / damaged stock" /></label>
      </div>
      <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy || !productId || !branchId}>{busy ? "Saving…" : "Save adjustment"}<span>↗</span></button></div>
    </form>}

    {/* Product catalog */}
    {products.length > 0 && <section className="surface-card" style={{ marginBottom: 16 }}>
      <div className="surface-card-heading"><div><p className="eyebrow">PRODUCT CATALOG</p><h2>All registered items.</h2></div></div>
      <div className="invoice-list">
        {products.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark">{(item.sku ?? item.name).slice(0, 3).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{item.name}</h3>
            <p>{item.product_type}{item.sku ? ` · SKU: ${item.sku}` : ""} · min: {item.minimum_stock} {item.unit}</p>
          </div>
          <div className="invoice-actions">
            <span className={`pipeline-status status-${item.status === "active" ? "paid" : "void"}`}>{item.status}</span>
            {can("inventory.manage") && <button className="text-control" disabled={busy} onClick={() => void toggleProductStatus(item)}>{item.status === "active" ? "Archive" : "Reactivate"}</button>}
          </div>
        </article>)}
      </div>
    </section>}

    {/* Stock list with filters */}
    <section className="surface-card inventory-card">
      <div className="surface-card-heading"><div><p className="eyebrow">BRANCH STOCK</p><h2>What is on hand.</h2></div><span className="muted-mono">{loading ? "SYNCING" : `${filteredStock.length} RECORD${filteredStock.length === 1 ? "" : "S"}`}</span></div>

      {stock.length > 0 && <div className="pipeline-toolbar" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input type="search" placeholder="Search products or branches…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 240, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />
          <div className="pipeline-tabs" role="tablist" style={{ fontSize: "0.78rem" }}>
            <button role="tab" aria-selected={typeFilter === "all"} className={typeFilter === "all" ? "active" : ""} onClick={() => setTypeFilter("all")}>All</button>
            {productTypes.map((t) => <button key={t} role="tab" aria-selected={typeFilter === t} className={typeFilter === t ? "active" : ""} onClick={() => setTypeFilter(t)}>{t}</button>)}
          </div>
        </div>
      </div>}

      {loading && <div className="dashboard-empty" role="status"><strong>Loading stock</strong><span>Checking authorized branches…</span></div>}
      {!loading && filteredStock.length === 0 && <div className="dashboard-empty"><strong>{search || typeFilter !== "all" ? "No matching stock records" : "No stock records yet"}</strong><span>Add a product, then record its first branch adjustment.</span></div>}
      {!loading && filteredStock.length > 0 && <div className="inventory-list">
        {filteredStock.map((item) => <article className={`inventory-row ${item.low_stock ? "is-low" : ""}`} key={item.id}>
          <div className="inventory-mark">{item.low_stock ? "!" : "·"}</div>
          <div>
            <div className="inventory-title"><h3>{item.product_name}</h3>{item.low_stock && <span className="pipeline-status status-lost">LOW STOCK</span>}</div>
            <p>{item.branch_name} · {item.product_type}</p>
            <small>{item.quantity} {item.unit} on hand · minimum {item.minimum_stock} {item.unit}</small>
          </div>
          <span className="inventory-quantity">{item.quantity}<small>{item.unit}</small></span>
        </article>)}
      </div>}
    </section>
  </main>;
}
