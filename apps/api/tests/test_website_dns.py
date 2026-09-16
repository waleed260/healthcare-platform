from types import SimpleNamespace

import dns.resolver

from app.modules.websites.dns import lookup_txt_proofs, verification_record_name


def test_verification_record_name_is_deterministic_and_normalized():
    assert verification_record_name("Example.TEST.") == "_carefully-verification.example.test"


def test_lookup_txt_proofs_joins_split_txt_segments(monkeypatch):
    monkeypatch.setattr(
        dns.resolver,
        "resolve",
        lambda *_args, **_kwargs: [SimpleNamespace(strings=(b"proof-", b"value"))],
    )
    assert lookup_txt_proofs("Example.TEST.") == ["proof-value"]


def test_lookup_txt_proofs_treats_missing_record_as_empty(monkeypatch):
    monkeypatch.setattr(dns.resolver, "resolve", lambda *_args, **_kwargs: (_ for _ in ()).throw(dns.resolver.NXDOMAIN()))
    assert lookup_txt_proofs("missing.example.test") == []
