"""Allow-listed report registry + safe query builder.

SECURITY: every piece of SQL a report emits comes from this module's fixed maps.
A saved report only stores KEYS (source/metric/dimension/filter names); those keys are
validated against the registry, and the emitted SQL interpolates only registry-defined
expressions. All user-supplied values (date range, filter values) are bound parameters,
and the clinic filter + RLS both scope every query. No user string ever reaches SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Source:
    label: str
    base: str                     # "FROM <table> WHERE clinic_id = :clinic_id [AND ...]"
    date_column: str
    permission: str
    metrics: dict[str, tuple[str, str]]       # key -> (sql_expr, label)
    dimensions: dict[str, tuple[str, str]]     # key -> (sql_expr, label)
    filters: dict[str, tuple[str, str]]        # key -> (column, "text"|"uuid")


SOURCES: dict[str, Source] = {
    "appointments": Source(
        label="Appointments & Care Flow",
        base="FROM appointments WHERE clinic_id = :clinic_id AND archived_at IS NULL",
        date_column="starts_at",
        permission="report.read",
        metrics={
            "count": ("COUNT(*)", "Appointments"),
            "completed": ("COUNT(*) FILTER (WHERE status = 'completed')", "Completed"),
            "cancelled": ("COUNT(*) FILTER (WHERE status = 'cancelled')", "Cancelled"),
            "no_show": ("COUNT(*) FILTER (WHERE status = 'no_show')", "No-shows"),
            "confirmed": ("COUNT(*) FILTER (WHERE status = 'confirmed')", "Confirmed"),
        },
        dimensions={
            "status": ("status", "Status"),
            "branch": ("branch_id", "Branch"),
            "day": ("date_trunc('day', starts_at)::date", "Day"),
            "month": ("date_trunc('month', starts_at)::date", "Month"),
        },
        filters={"status": ("status", "text"), "branch": ("branch_id", "uuid")},
    ),
    "package_sales": Source(
        label="Package Sales & Utilization",
        base="FROM patient_packages WHERE clinic_id = :clinic_id",
        date_column="purchased_at",
        permission="package.read",
        metrics={
            "count": ("COUNT(*)", "Packages sold"),
            "active": ("COUNT(*) FILTER (WHERE status = 'active')", "Active"),
            "sessions_purchased": ("COALESCE(SUM(total_sessions), 0)", "Sessions purchased"),
            "sessions_used": ("COALESCE(SUM(used_sessions), 0)", "Sessions used"),
            "sessions_remaining": ("COALESCE(SUM(GREATEST(total_sessions - used_sessions, 0)), 0)", "Sessions remaining"),
        },
        dimensions={
            "status": ("status", "Status"),
            "package": ("package_definition_id", "Package"),
            "day": ("date_trunc('day', purchased_at)::date", "Day"),
            "month": ("date_trunc('month', purchased_at)::date", "Month"),
        },
        filters={"status": ("status", "text"), "package": ("package_definition_id", "uuid")},
    ),
    "payments": Source(
        label="Cash Collections",
        base="FROM payments WHERE clinic_id = :clinic_id",
        date_column="paid_at",
        permission="report.read",
        metrics={
            "collected_minor": ("COALESCE(SUM(amount_minor), 0)", "Collected (minor units)"),
            "payment_count": ("COUNT(*)", "Payments"),
        },
        dimensions={
            "method": ("method", "Method"),
            "day": ("date_trunc('day', paid_at)::date", "Day"),
            "month": ("date_trunc('month', paid_at)::date", "Month"),
        },
        filters={"method": ("method", "text")},
    ),
    "invoices": Source(
        label="Billing (Invoiced)",
        base="FROM invoices WHERE clinic_id = :clinic_id AND status <> 'void'",
        date_column="issued_at",
        permission="report.read",
        metrics={
            "invoiced_minor": ("COALESCE(SUM(total_minor), 0)", "Invoiced (minor units)"),
            "invoice_count": ("COUNT(*)", "Invoices"),
            "paid_count": ("COUNT(*) FILTER (WHERE status = 'paid')", "Paid invoices"),
        },
        dimensions={
            "status": ("status", "Status"),
            "day": ("date_trunc('day', issued_at)::date", "Day"),
            "month": ("date_trunc('month', issued_at)::date", "Month"),
        },
        filters={"status": ("status", "text")},
    ),
    "package_financials": Source(
        label="Package Financials (invoiced vs collected vs refunds)",
        base=(
            "FROM patient_packages pp "
            "LEFT JOIN invoices i ON i.clinic_id = pp.clinic_id AND i.id = pp.invoice_id AND i.status <> 'void' "
            "LEFT JOIN LATERAL (SELECT COALESCE(SUM(amount_minor), 0) AS collected FROM payments "
            "WHERE clinic_id = pp.clinic_id AND invoice_id = pp.invoice_id) pay ON true "
            "LEFT JOIN LATERAL (SELECT COALESCE(SUM(amount_minor), 0) AS refunded FROM refunds "
            "WHERE clinic_id = pp.clinic_id AND invoice_id = pp.invoice_id) ref ON true "
            "WHERE pp.clinic_id = :clinic_id"
        ),
        date_column="pp.purchased_at",
        permission="package.read",
        metrics={
            "count": ("COUNT(*)", "Packages sold"),
            "invoiced_minor": ("COALESCE(SUM(i.total_minor), 0)", "Invoiced (minor units)"),
            "collected_minor": ("COALESCE(SUM(pay.collected), 0)", "Collected (minor units)"),
            "refunds_minor": ("COALESCE(SUM(ref.refunded), 0)", "Refunds (minor units)"),
            "net_collected_minor": ("COALESCE(SUM(pay.collected - ref.refunded), 0)", "Net collected (minor units)"),
            "sessions_purchased": ("COALESCE(SUM(pp.total_sessions), 0)", "Sessions purchased"),
            "sessions_used": ("COALESCE(SUM(pp.used_sessions), 0)", "Sessions used"),
        },
        dimensions={
            "status": ("pp.status", "Status"),
            "package": ("pp.package_definition_id", "Package"),
            "day": ("date_trunc('day', pp.purchased_at)::date", "Day"),
            "month": ("date_trunc('month', pp.purchased_at)::date", "Month"),
        },
        filters={"status": ("pp.status", "text"), "package": ("pp.package_definition_id", "uuid")},
    ),
}

_PRESETS = {"7d": 7, "30d": 30, "90d": 90, "180d": 180, "365d": 365}
MAX_ROWS = 2000


def catalog() -> list[dict]:
    """Builder catalog: every source with its allowed metrics/dimensions/filters."""
    return [
        {
            "key": key,
            "label": src.label,
            "permission": src.permission,
            "metrics": [{"key": k, "label": lbl} for k, (_e, lbl) in src.metrics.items()],
            "dimensions": [{"key": k, "label": lbl} for k, (_e, lbl) in src.dimensions.items()],
            "filters": [{"key": k, "type": typ} for k, (_c, typ) in src.filters.items()],
        }
        for key, src in SOURCES.items()
    ]


def _resolve_range(preset: str, start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    if start is not None or end is not None:
        lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) if start else None
        hi = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1) if end else None
        return lo, hi
    if preset == "all":
        return None, None
    return datetime.now(timezone.utc) - timedelta(days=_PRESETS[preset]), None


def run_report(db: Session, clinic_id: UUID, config: "ReportConfigLike") -> dict:
    """Execute a validated report config and return {columns, rows}. Assumes the caller
    already set tenant context and validated the config against the registry."""
    src = SOURCES[config.source]
    select_parts: list[str] = []
    columns: list[dict] = []
    for d in config.group_by:
        expr, label = src.dimensions[d]
        select_parts.append(f"{expr} AS {d}")
        columns.append({"key": d, "label": label, "kind": "dimension"})
    for m in config.metrics:
        expr, label = src.metrics[m]
        select_parts.append(f"{expr} AS {m}")
        columns.append({"key": m, "label": label, "kind": "metric"})

    where = [src.base]
    params: dict = {"clinic_id": str(clinic_id)}
    lo, hi = _resolve_range(config.range_preset, config.start, config.end)
    if lo is not None:
        where.append(f"{src.date_column} >= :range_start")
        params["range_start"] = lo
    if hi is not None:
        where.append(f"{src.date_column} < :range_end")
        params["range_end"] = hi
    for i, (fkey, fval) in enumerate(config.filters.items()):
        col, typ = src.filters[fkey]
        pname = f"flt_{i}"
        where.append(f"{col} = :{pname}")
        params[pname] = UUID(str(fval)) if typ == "uuid" else str(fval)

    sql = "SELECT " + ", ".join(select_parts) + " " + " AND ".join(where)
    if config.group_by:
        sql += " GROUP BY " + ", ".join(str(i + 1) for i in range(len(config.group_by)))
        sql += " ORDER BY " + ", ".join(str(i + 1) for i in range(len(config.group_by)))
    sql += f" LIMIT {MAX_ROWS}"
    rows = db.execute(text(sql), params).mappings().all()
    return {"columns": columns, "rows": [dict(r) for r in rows]}
