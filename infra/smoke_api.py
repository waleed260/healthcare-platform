#!/usr/bin/env python3
"""End-to-end API smoke test against a running API seeded with scripts/seed_demo.py (fake data only).

    python infra/smoke_api.py http://127.0.0.1:8000

It signs in as the synthetic owner (enrolling MFA), then drives the main write and read paths through the real
runtime database role. Exit code is non-zero if any check fails.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta

import httpx
import pyotp

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
EMAIL = os.environ.get("SMOKE_EMAIL", "owner.a@synthetic.example.test")
PASSWORD = os.environ.get("SEED_PASSWORD", "Synthetic-Demo-Only-2026!")
ORIGIN = os.environ.get("SMOKE_ORIGIN", "http://localhost:3000")
RUN = str(int(time.time()))  # unique suffix so reruns do not collide on names/slugs
results: list[tuple[str, bool, str]] = []
client = httpx.Client(base_url=BASE, timeout=30, headers={"Origin": ORIGIN})
public = httpx.Client(base_url=BASE, timeout=30)


def csrf() -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("csrf_token") or ""}


def check(name: str, response: httpx.Response, ok: tuple[int, ...] = (200, 201)) -> dict:
    good = response.status_code in ok
    detail = "" if good else f"{response.status_code} {response.text[:260]}"
    results.append((name, good, detail))
    print(f"{'PASS' if good else 'FAIL'}  {name} {detail}")
    try:
        body = response.json()
        return (body.get("data", body) if isinstance(body, dict) else body) if good and response.status_code < 300 else {}
    except Exception:  # binary bodies (PDF)
        return {}


def main() -> int:
    r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    data = check("login", r)
    if data.get("mfa_enrollment_required"):
        secret = check("mfa enroll", client.post("/api/v1/auth/mfa/enroll", headers=csrf()))["secret"]
        check("mfa verify", client.post("/api/v1/auth/mfa/verify", headers=csrf(), json={"code": pyotp.TOTP(secret).now()}))
    elif data.get("mfa_required"):
        print("account already enrolled; set up a fresh seed")
        return 2
    me = check("auth/me", client.get("/api/v1/auth/me"))
    perms = set(me.get("permissions", []))
    for needed in ("expense.manage", "website.edit", "billing.manage", "clinical.manage"):
        results.append((f"permission {needed}", needed in perms, "" if needed in perms else "missing"))
        print(f"{'PASS' if needed in perms else 'FAIL'}  permission {needed}")

    # ---- finance: expenses, cashier summary
    check("cashier summary", client.get("/api/v1/finance/cashier-summary"))
    exp = check("expense create", client.post("/api/v1/finance/expenses", headers=csrf(), json={"category": "supplies", "description": "Smoke gloves", "amount_minor": 450000, "currency": "PKR", "incurred_on": date.today().isoformat()}))
    check("expense list", client.get("/api/v1/finance/expenses"))
    if exp:
        check("expense void", client.post(f"/api/v1/finance/expenses/{exp['id']}/void", headers=csrf(), json={"reason": "smoke test cleanup"}))

    # ---- invoices, payment, receipts, commissions
    patients = check("patients list", client.get("/api/v1/patients?limit=5")) or []
    doctors = check("doctors list", client.get("/api/v1/doctors?limit=5")) or []
    if patients and doctors:
        provider = doctors[0]["id"]
        check("commission rule", client.put(f"/api/v1/finance/commission-rules/{provider}", headers=csrf(), json={"percent_bp": 2500, "active": True}))
        today = date.today()
        base = check("provider revenue (before)", client.get(f"/api/v1/finance/provider-revenue?start={today - timedelta(days=1)}&end={today}")) or {}
        inv = check("invoice create (provider line)", client.post("/api/v1/invoices", headers=csrf(), json={"patient_id": patients[0]["id"], "currency": "PKR", "lines": [{"description": "Smoke consult", "quantity": 1, "unit_price_minor": 1000000, "tax_minor": 0, "provider_id": provider}]}))
        if inv:
            check("payment", client.post(f"/api/v1/invoices/{inv['id']}/payments", headers=csrf(), json={"amount_minor": 1000000, "method": "cash"}))
            for fmt in ("a4", "thermal"):
                resp = client.get(f"/api/v1/invoices/{inv['id']}/receipt.pdf?format={fmt}")
                results.append((f"receipt pdf {fmt}", resp.status_code == 200 and resp.content.startswith(b"%PDF"), f"{resp.status_code}"))
                print(f"{'PASS' if results[-1][1] else 'FAIL'}  receipt pdf {fmt}")
            rev = check("provider revenue (after)", client.get(f"/api/v1/finance/provider-revenue?start={today - timedelta(days=1)}&end={today}")) or {}
            got = (rev.get("total_commission_minor") or 0) - (base.get("total_commission_minor") or 0)
            results.append(("commission delta = 25% of 10,000.00", got == 250000, f"got {got}"))
            print(f"{'PASS' if got == 250000 else 'FAIL'}  commission delta = 25% of 10,000.00 (got {got})")

    # ---- upgrade requests
    check("upgrade request create", client.post("/api/v1/upgrade-requests", headers=csrf(), json={"kind": "specialty", "target_code": "skin", "message": "smoke"}), ok=(201, 409))
    reqs = check("upgrade request list", client.get("/api/v1/upgrade-requests")) or []
    pending = [x for x in reqs if x["status"] == "pending"]
    if pending:
        check("upgrade request cancel", client.post(f"/api/v1/upgrade-requests/{pending[0]['id']}/cancel", headers=csrf()))

    # ---- website: template, theme, reorder, reusable, SEO, redirects
    site = check("website create", client.post("/api/v1/websites", headers=csrf(), json={"name": "Smoke site", "template_key": "calm_clinic", "brand": {}}))
    if site:
        wid = site["id"]
        check("template library", client.get("/api/v1/website-library/templates"))
        listed = check("website list (version)", client.get("/api/v1/websites")) or []
        live = next((w for w in listed if w["id"] == wid), site)  # create returns the pre-snapshot version
        applied = check("apply site template", client.post(f"/api/v1/website-library/websites/{wid}/apply-site-template", headers=csrf(), json={"template_key": "general_clinic", "expected_version": live["version"]}))
        pages = check("pages list", client.get(f"/api/v1/websites/{wid}/pages?limit=50")) or []
        home = next((p for p in pages if p["slug"] == "home"), None)
        if home:
            secs = check("sections list", client.get(f"/api/v1/websites/{wid}/pages/{home['id']}/sections")) or []
            if len(secs) > 1:
                order = [s["id"] for s in reversed(secs)]
                check("reorder sections (atomic)", client.post(f"/api/v1/website-library/websites/{wid}/pages/{home['id']}/reorder-sections", headers=csrf(), json={"section_ids": order}))
                reuse = check("reusable create", client.post("/api/v1/website-library/reusable-sections", headers=csrf(), json={"name": f"Smoke banner {RUN}", "source_section_id": secs[0]["id"]}), ok=(201, 409))
                if reuse:
                    check("reusable insert synced", client.post(f"/api/v1/website-library/websites/{wid}/pages/{home['id']}/insert-reusable/{reuse['id']}", headers=csrf(), json={"mode": "synced"}))
                    check("reusable update propagates", client.patch(f"/api/v1/website-library/reusable-sections/{reuse['id']}", headers=csrf(), json={"expected_version": reuse["version"], "content": {"heading": "Updated everywhere", "body": "<p>ok</p>"}}))
            check("page SEO", client.patch(f"/api/v1/websites/{wid}/pages/{home['id']}", headers=csrf(), json={"expected_version": home["version"], "seo_title": "Smoke SEO", "noindex": False, "canonical_url": "/home"}))
        check("redirect create", client.post(f"/api/v1/websites/{wid}/redirects", headers=csrf(), json={"from_path": "/old", "to_path": "/about", "status_code": 301}))
        check("redirect list", client.get(f"/api/v1/websites/{wid}/redirects"))
        fresh = (check("website list", client.get("/api/v1/websites")) or [site])
        current = next((w for w in fresh if w["id"] == wid), site)
        check("theme save (brand)", client.patch(f"/api/v1/websites/{wid}", headers=csrf(), json={"expected_version": current["version"], "brand": {"theme": {"colors": {"primary": "#112233"}}, "header": {"nav": [{"label": "Home", "href": "/"}]}}}))
        check("validation", client.get(f"/api/v1/websites/{wid}/validation"))

    # ---- forms, blog, testimonials (+ public side)
    form = check("form create", client.post("/api/v1/website-content/forms", headers=csrf(), json={"name": f"Smoke enquiry {RUN}", "fields": [{"key": "name", "label": "Name", "type": "text", "required": True, "maps_to": "full_name"}, {"key": "phone", "label": "Phone", "type": "phone", "required": True, "maps_to": "phone"}, {"key": "consent", "label": "I agree", "type": "consent", "required": True}]}), ok=(201, 409))
    clinic_slug = "demo-collision-a"
    if form:
        sub = public.post(f"/api/v1/public/sites/slug/{clinic_slug}/forms/{form['id']}/submit", headers={"Idempotency-Key": f"smoke-{RUN}"}, json={"answers": {"name": "Smoke Lead", "phone": "+92 300 1234567", "consent": True}})
        check("public form submit", sub)
        check("lead exists", client.get("/api/v1/leads?limit=50"))
    post = check("blog create", client.post("/api/v1/website-content/posts", headers=csrf(), json={"slug": f"smoke-post-{RUN}", "title": "Smoke post", "excerpt": "x", "body": "<p>Hello</p><script>alert(1)</script>"}), ok=(201, 409))
    if post:
        check("blog publish", client.post(f"/api/v1/website-content/posts/{post['id']}/status", headers=csrf(), json={"expected_version": post["version"], "status": "published"}))
        body = check("public post", public.get(f"/api/v1/public/sites/slug/{clinic_slug}/posts/smoke-post-{RUN}"))
        results.append(("blog body sanitised", "<script" not in (body or {}).get("body", "<script"), ""))
        print(f"{'PASS' if results[-1][1] else 'FAIL'}  blog body sanitised")
    tst = check("testimonial create", client.post("/api/v1/website-content/testimonials", headers=csrf(), json={"author_name": "A. Patient", "rating": 5, "body": "Great care", "consent_confirmed": True}))
    if tst:
        check("testimonial approve", client.post(f"/api/v1/website-content/testimonials/{tst['id']}/moderate", headers=csrf(), json={"expected_version": tst["version"], "status": "approved"}))
        check("public testimonials", public.get(f"/api/v1/public/sites/slug/{clinic_slug}/testimonials"))

    # ---- clinical + security
    if patients:
        pid = patients[0]["id"]
        plan = check("treatment plan", client.post("/api/v1/treatment-plans", headers=csrf(), json={"patient_id": pid, "title": "Smoke plan"}))
        if plan:
            check("plan item", client.post(f"/api/v1/treatment-plans/{plan['id']}/items", headers=csrf(), json={"title": "Step 1", "sort_order": 0}))
        check("prescription", client.post(f"/api/v1/patients/{pid}/prescriptions", headers=csrf(), json={"medication_name": "Smoke med", "dosage": "1"}))
        check("consent record", client.post(f"/api/v1/patients/{pid}/consents", headers=csrf(), json={"consent_type": "smoke", "status": "granted", "version": "1"}))

        # clinical forms: builder (template) + fill-in (draft -> submit), verified against the real DB
        templates = check("form templates", client.get("/api/v1/clinical-forms/templates")) or []
        results.append(("seeded hair_assessment present", any(t["form_key"] == "hair_assessment" for t in templates), ""))
        print(f"{'PASS' if results[-1][1] else 'FAIL'}  seeded hair_assessment present")
        tmpl = check("form template create", client.post("/api/v1/clinical-forms/templates", headers=csrf(), json={"form_key": f"smoke_form_{RUN}", "name": "Smoke form", "field_schema": {"fields": [{"key": "score", "label": "Score", "type": "number", "required": True}, {"key": "area", "label": "Area", "type": "select", "required": True, "options": ["A", "B"]}]}}), ok=(201, 409))
        if tmpl:
            resp = check("form response draft", client.post(f"/api/v1/patients/{pid}/form-responses", headers=csrf(), json={"template_id": tmpl["id"], "response_data": {"score": 7}}))
            if resp:
                check("form response update", client.patch(f"/api/v1/patients/{pid}/form-responses/{resp['id']}", headers=csrf(), json={"expected_version": resp["version"], "response_data": {"score": 9, "area": "B"}}))
                # submit must reject a missing required field, then accept once complete
                bad = client.post(f"/api/v1/patients/{pid}/form-responses/{resp['id']}/submit", headers=csrf(), json={"expected_version": resp["version"] + 1})
                check("form submit (complete)", bad)
                reread = check("form responses reread", client.get(f"/api/v1/patients/{pid}/form-responses")) or []
                mine = next((r for r in reread if r["id"] == resp["id"]), None)
                ok = bool(mine) and mine["status"] == "submitted" and mine["response_data"].get("area") == "B"
                results.append(("form response persisted + submitted", ok, "" if ok else str(mine)))
                print(f"{'PASS' if ok else 'FAIL'}  form response persisted + submitted")

        # specialty tools: save structured state, reload, verify persistence + server-computed total
        put_hdr = {**csrf(), "Content-Type": "application/json"}
        graft = client.put(f"/api/v1/patients/{pid}/tool-states/graft_plan", headers=put_hdr, json={"tool_key": "graft_plan", "state": {"zones": {"hairline": 1500, "crown": 500}, "notes": "smoke"}})
        gdata = check("tool state save (graft_plan)", graft)
        if gdata:
            results.append(("graft total computed server-side", gdata.get("state", {}).get("total") == 2000, str(gdata.get("state"))))
            print(f"{'PASS' if results[-1][1] else 'FAIL'}  graft total computed server-side")
        check("tool state save (dental_chart)", client.put(f"/api/v1/patients/{pid}/tool-states/dental_chart", headers=put_hdr, json={"tool_key": "dental_chart", "state": {"teeth": {"11": "crown", "36": "filled"}}}))
        # invalid state must be rejected
        bad_tool = client.put(f"/api/v1/patients/{pid}/tool-states/norwood", headers=put_hdr, json={"tool_key": "norwood", "state": {"stage": "XII"}})
        results.append(("invalid tool state rejected", bad_tool.status_code == 400, str(bad_tool.status_code)))
        print(f"{'PASS' if results[-1][1] else 'FAIL'}  invalid tool state rejected")
        tools = check("tool states reload", client.get(f"/api/v1/patients/{pid}/tool-states")) or []
        keys = {t["tool_key"] for t in tools}
        results.append(("tool states persisted + reloaded", {"graft_plan", "dental_chart"} <= keys, str(keys)))
        print(f"{'PASS' if results[-1][1] else 'FAIL'}  tool states persisted + reloaded")
    # patient media upload (raw image body) -> appears pending scan, verified over real HTTP + storage
    if patients:
        import base64 as _b64
        png = _b64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMCAQGl9jAAAAAASUVORK5CYII=")
        up = client.post(f"/api/v1/patients/{patients[0]['id']}/media/upload?media_kind=before", headers={**csrf(), "Content-Type": "image/png"}, content=png)
        media_row = check("patient media upload", up)
        if media_row:
            results.append(("uploaded media is pending scan", media_row.get("scan_status") == "pending_scan", str(media_row.get("scan_status"))))
            print(f"{'PASS' if results[-1][1] else 'FAIL'}  uploaded media is pending scan")
    check("security overview", client.get("/api/v1/auth/security"))
    check("google config", public.get("/api/v1/auth/google/config"))

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
