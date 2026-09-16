"""DNS proof lookup for custom website host verification."""

from __future__ import annotations


DNS_RECORD_PREFIX = "_carefully-verification"


class DnsLookupUnavailable(RuntimeError):
    """The resolver could not provide a trustworthy answer."""


def verification_record_name(hostname: str) -> str:
    return f"{DNS_RECORD_PREFIX}.{hostname.strip().rstrip('.').casefold()}"


def lookup_txt_proofs(hostname: str) -> list[str]:
    """Return TXT values, treating missing records as an empty proof set."""
    try:
        import dns.exception
        import dns.resolver
    except ImportError as exc:  # pragma: no cover - packaging failure path
        raise DnsLookupUnavailable("DNS resolver dependency is unavailable") from exc
    try:
        answers = dns.resolver.resolve(verification_record_name(hostname), "TXT", lifetime=3.0)
    except (dns.exception.Timeout, dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return []
    values: list[str] = []
    for answer in answers:
        value = b"".join(answer.strings).decode("utf-8", errors="strict").strip()
        if value:
            values.append(value)
    return values
