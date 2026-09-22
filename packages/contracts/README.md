# Shared API contract

`openapi.json` is generated from the FastAPI application and is the canonical
API description for the web client and release review. Export it from the
repository root with:

```bash
PYTHONPATH=apps/api python apps/api/scripts/export_openapi.py
```

CI regenerates the artifact and fails when the committed contract is stale.
The finite literal types in `openapi-types.ts` are generated from this file with
`python3 packages/contracts/generate_types.py`; CI fails if the checked-in output
is stale. Frontend code must not redefine API status enums or permission codes
independently.
