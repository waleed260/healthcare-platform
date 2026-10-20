"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, money, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type Product = { id: string; name: string; sku: string | null; product_type: string | null; unit: string; minimum_stock: string; status: string; version: number; category_id: string | null; cost_minor: number | null; selling_price_minor: number | null; currency: string | null; tax_inclusive: boolean };
type Stock = { id: string; branch_id: string; branch_name: string; product_id: string; product_name: string; product_type: string | null; unit: string; minimum_stock: string; category_id: string | null; quantity: string; low_stock: boolean; version: number };
type Branch = { id: string; name: string };
type Category = { id: string; name: string; slug: string; display_order: number };
type Session = { permissions?: string[] };

const UNIT_OPTIONS = ["Pieces", "mg", "ml", "g", "kg", "L", "Box", "Pack", "Tablet", "Capsule", "Vial", "Ampoule", "Tube"] as const;

export default function InventoryPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [stock, setStock] = useState<Stock[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showProduct, setShowProduct] = useState(false);
  const [showAdjustment, setShowAdjustment] = useState(false);
  const [showCategory, setShowCategory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  const can = (permission: string) => permissions.includes(permission);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, productRows, stockRows, branchRows, categoryRows] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Product[]>("/api/v1/inventory/products?limit=100"),
        api<Stock[]>("/api/v1/inventory/stock"),
        api<Branch[]>("/api/v1/branches?limit=100"),
        api<Category[]>("/api/v1/inventory/categories").catch(() => []),
      ]);
      setPermissions(session.permissions ?? []);
      setProducts(productRows ?? []);
      setStock(stockRows ?? []);
      setBranches(branchRows ?? []);
      setCategories(categoryRows ?? []);
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
    if (categoryFilter !== "all") {
      result = result.filter((s) => s.category_id === categoryFilter);
    }
    return result;
  }, [stock, search, typeFilter, categoryFilter]);

  const productTypes = useMemo(() => {
    const types = new Set(stock.map((s) => s.product_type).filter(Boolean));
    return Array.from(types).sort() as string[];
  }, [stock]);

  async function createProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const effectiveUnit = unit === "custom" ? customUnit : unit;
      await post("/api/v1/inventory/products", {
        name,
        sku: sku || null,
        product_type: type || null,
        unit: effectiveUnit,
        minimum_stock: minimum,
        category_id: selectedCategoryId || null,
        cost_minor: costMinor ? Math.round(Number(costMinor) * 100) : null,
        selling_price_minor: sellingPrice ? Math.round(Number(sellingPrice) * 100) : null,
        tax_inclusive: taxInclusive,
      });
      setName(""); setSku(""); setMinimum("0"); setUnit("Pieces"); setCustomUnit("");
      setCostMinor(""); setSellingPrice(""); setTaxInclusive(false); setSelectedCategoryId("");
      setShowProduct(false);
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

  async function createCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await post("/api/v1/inventory/categories", { name: categoryName, slug: categorySlug });
      setCategoryName(""); setCategorySlug(""); setShowCategory(false);
      toast.success("Category created.");
      await load();
    } catch (reasonValue) {
      toast.error(errorMessage(reasonValue, "The category could not be created."));
    } finally {
      setBusy(false);
    }
  }

  async function deleteCategory(id: string, categoryDisplayName: string) {
    const ok = await confirm({ message: `Delete category "${categoryDisplayName}"? Products in this category will become uncategorized.`, danger: true });
    if (!ok) return;
    setBusy(true);
    try {
      await api(`/api/v1/inventory/categories/${id}`, { method: "DELETE", headers: writeHeaders() });
      toast.success("Category deleted.");
      await load();
    } catch (reasonValue) {
      toast.error(errorMessage(reasonValue, "The category could not be deleted."));
    } finally {
      setBusy(false);
    }
  }

  const categoryMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of categories) m.set(c.id, c.name);
    return m;
  }, [categories]);

  const lowCount = stock.filter((item) => item.low_stock).length;
  return <main className="workspace-page inventory-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">OPERATIONS</p>
        <h1>Know what is <em>running low.</em></h1>
        <p className="workspace-page-intro">Products, medicines, consumables, and materials by branch, with every adjustment explained.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        {can("inventory.manage") && <>
          <button className="button button-secondary" onClick={() => setShowCategory((v) => !v)}>Categories <span>⚙</span></button>
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

    {/* Category Management */}
    {showCategory && <section className="surface-card inventory-form">
      <div className="surface-card-heading"><div><p className="eyebrow">CATEGORIES</p><h2>Organize your inventory.</h2></div></div>
      {categories.length > 0 && <div className="invoice-list" style={{ marginBottom: 16 }}>
        {categories.map((c) => <article className="invoice-row" key={c.id}>
          <div className="invoice-main"><h3>{c.name}</h3><p>{c.slug}</p></div>
          <div className="invoice-actions">
            <button className="text-control" disabled={busy} onClick={() => void deleteCategory(c.id, c.name)}>Delete</button>
          </div>
        </article>)}
      </div>}
      <form onSubmit={createCategory} style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <label style={{ flex: 1, minWidth: 160 }}>Name<input required value={categoryName} onChange={(e) => setCategoryName(e.target.value)} placeholder="Instruments" /></label>
        <label style={{ flex: 1, minWidth: 160 }}>Slug<input required value={categorySlug} onChange={(e) => setCategorySlug(e.target.value)} placeholder="instruments" pattern="^[a-z0-9][a-z0-9-]*$" /></label>
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add category"}<span>＋</span></button>
      </form>
    </section>}

    {/* New Product Form */}
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
      <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add product"}<span>↗</span></button></div>
    </form>}

    {/* Stock Adjustment Form */}
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
            <p>{item.branch_name} · {item.product_type ?? "uncategorized"}{item.category_id && categoryMap.has(item.category_id) ? ` · ${categoryMap.get(item.category_id)}` : ""}</p>
            <small>{item.quantity} {item.unit} on hand · minimum {item.minimum_stock} {item.unit}</small>
          </div>
          <span className="inventory-quantity">{item.quantity}<small>{item.unit}</small></span>
        </article>)}
      </div>}
    </section>
  </main>;
}
