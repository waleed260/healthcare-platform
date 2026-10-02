"""Dependency-free receipt rendering: A4 invoices and 80 mm thermal receipts as PDF or HTML."""
from __future__ import annotations

from html import escape
from typing import Any, Literal

ReceiptFormat = Literal["a4", "thermal"]

_A4 = (595, 842)
_THERMAL_WIDTH = 227  # 80 mm in PDF points


def money(minor: int, currency: str) -> str:
    return f"{currency.strip()} {minor / 100:,.2f}"


def _lines(data: dict[str, Any], width: int) -> list[str]:
    invoice, patient, clinic = data["invoice"], data["patient"], data["clinic"]
    cur = invoice["currency"]
    rule = "-" * width
    out = [clinic["name"].upper()[:width], rule, f"Invoice {invoice['invoice_number']}", f"Date   {str(invoice['issued_at'])[:16]}", f"Patient {patient['name']} ({patient['patient_number']})", rule]
    for line in data["lines"]:
        out.append(str(line["description"])[:width])
        out.append(f"  {line['quantity']} x {money(line['unit_price_minor'], cur)} = {money(line['line_total_minor'], cur)}")
    out += [rule, f"Subtotal {money(invoice['subtotal_minor'], cur)}", f"Discount {money(invoice['discount_minor'], cur)}", f"Tax      {money(invoice['tax_minor'], cur)}", f"TOTAL    {money(invoice['total_minor'], cur)}", rule]
    for payment in data["payments"]:
        out.append(f"Paid {money(payment['amount_minor'], cur)} by {payment['method']} on {str(payment['paid_at'])[:10]}")
    out += [f"Paid total {money(invoice['paid_minor'], cur)}", f"BALANCE    {money(invoice['balance_minor'], cur)}", f"Status: {invoice['status'].replace('_', ' ')}"]
    if invoice.get("notes"):
        out += [rule, str(invoice["notes"])[:width * 3]]
    return out


def _pdf_escape(value: str) -> str:
    safe = value.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_pdf(data: dict[str, Any], fmt: ReceiptFormat) -> bytes:
    """Render a single-page text PDF using the built-in Helvetica font."""
    thermal = fmt == "thermal"
    columns = 34 if thermal else 78
    text_lines = _lines(data, columns)
    leading = 11 if thermal else 15
    font = 8 if thermal else 11
    margin = 12 if thermal else 48
    width = _THERMAL_WIDTH if thermal else _A4[0]
    height = max(200, margin * 2 + leading * (len(text_lines) + 1)) if thermal else _A4[1]
    commands = [f"BT /F1 {font} Tf {leading} TL {margin} {height - margin - font} Td"]
    for line in text_lines[: (height - margin * 2) // leading]:
        commands.append(f"({_pdf_escape(line)}) Tj T*")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def render_html(data: dict[str, Any], fmt: ReceiptFormat) -> str:
    thermal = fmt == "thermal"
    width = "80mm" if thermal else "210mm"
    body = escape("\n".join(_lines(data, 34 if thermal else 78)))
    title = escape(f"Invoice {data['invoice']['invoice_number']}")
    return (
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{title}</title>"
        f"<style>@page{{size:{'80mm auto' if thermal else 'A4'};margin:8mm}}body{{margin:0;font:{'11px' if thermal else '13px'}/1.5 'Courier New',monospace}}"
        f"pre{{width:{width};max-width:100%;margin:0 auto;white-space:pre-wrap}}</style></head><body><pre>{body}</pre></body></html>"
    )
