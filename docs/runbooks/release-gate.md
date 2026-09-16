# Production release gate

Create a JSON evidence manifest only after the corresponding checks have been
run in staging with synthetic data. Missing evidence is a failed gate.

```bash
python3 infra/release_gate.py /restricted/release-evidence.json
```

The manifest must contain the boolean gates named in `infra/release_gate.py`
and a `metrics` object containing the measured API, availability, booking,
dashboard, Web Vitals, RPO, and RTO values. Values are compared against the
numeric targets in specification sections 23 and 30.

Every measurement must be finite and non-negative; missing, boolean, NaN, and
infinite values fail closed.

Attach deployment version, synthetic dataset cardinalities, timestamps, test
links, restore record, security scan output, manual WCAG review, monitoring and
rollback drill, retention approval, and pilot owner approval beside the
manifest. Never put credentials, patient data, tokens, signed URLs, or secrets
in the evidence bundle.
