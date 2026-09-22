# Phase 6 website traceability

| Requirement | Evidence |
| --- | --- |
| Controlled templates and sections | `websites.template_key`, section type/layout constraints in migration |
| Draft/live version topology | `website_versions`, draft/live version references, immutable checksum field, and transactional draft snapshot regeneration after editor mutations |
| Tenant-safe website content | Composite tenant FKs and forced RLS on all website tables |
| Safe rich text and navigation | `app/modules/websites/sanitizer.py` allowlist, `validate_navigation_href`, and sanitizer tests |
| Backend-protected editing | Website/page/section CRUD commands require `website.edit` and CSRF; reads require `website.read` |
| No arbitrary HTML/JS and contrast gate | Pydantic section schema, Bleach allowlist, and WCAG AA contrast validation in publish/rollback validation |

Publishing validation, atomic live-version swaps, rollback, DNS TXT proof verification, exact verified-host resolution, and immutable snapshot protection are implemented in `0015_website_publishing.py`, `app/modules/websites/publishing.py`, `app/modules/websites/dns.py`, and `app/modules/websites/routes.py`. Website/page/section/media CRUD now uses controlled schemas, expected-version locking from `0038_website_content_versioning.py` and `0039_website_media_versioning.py`, safe navigation validation, tenant scoping, audit events, and transactional draft snapshot regeneration. Public host lookup first resolves an exact verified hostname, then sets the tenant context before reading the live snapshot. Automated axe coverage now includes the public booking and staff surfaces; remaining work is certificate/DNS provider provisioning evidence and manual contrast/WCAG evidence.
The authenticated `/website` editor now consumes the tenant-scoped APIs for page and section draft editing, optimistic saves, publish, immutable version history, and confirmed rollback; browser coverage exercises draft save and publish on desktop and mobile.
Website media and domain verification commands are now exposed under `/api/v1/websites`. Media is restricted to safe image MIME types, receives generated private draft keys, and remains pending scan/non-public. Hostnames are normalized and validated; DNS proofs are returned once and only their hashes are stored, with verified status required for public host resolution.
Short-lived hashed website preview tokens are provided by `/preview-token`; the
verified-host draft preview endpoint accepts the token in a header and returns
`X-Robots-Tag: noindex, nofollow, noarchive`. Preview tokens are revoked when a
website is published or rolled back.
Uploaded website images use `POST /api/v1/websites/media/upload` with a private
server-generated draft key. The endpoint enforces an 8 MiB limit, JPEG/PNG/WebP
extension and magic-byte checks, records SHA-256 and size metadata, and queues
an idempotent `website_media_scan` job. Media stays `pending_scan` and
non-public until the scanner confirms the stored object.

Publishing rejects any unclean draft media, copies clean objects to immutable
versioned public keys, and marks them public in the same database transaction.
Published assets are served only through an exact verified hostname and a
tenant-scoped media lookup; unknown hosts and draft/non-public media return a
neutral 404. Public site, preview, and media resolution also requires the
owning clinic to be active and non-archived.

Each website-media scan decision is retained in the tenant-scoped
`website_media_scan_events` table with engine, signature version, outcome,
failure reason, and timestamp.
