# Threat model and risk inventory

Assets: private records/labels, account hashes, sessions, immutable dataset versions,
job requests/results, reports, evaluation receipts, configuration and backup contents.
Boundaries: browser → TLS proxy → Next bridge → API → worker/SQLite/ledger; separately,
privileged operators → host filesystem. Attackers considered are unauthenticated
callers, another account/guest and malicious CSV content. A hostile host administrator
or compromised installed dependency is outside application isolation.

| Threat / priority | Mitigation and validation | Residual risk |
|---|---|---|
| Cross-owner access, deletion, cached reports / P0 | Server ownership checks; two-account/two-guest and all-route regression suite | No independent penetration test |
| Session fixation/theft, CSRF / P0 | Rotation/revocation, hashed random tokens, HttpOnly/SameSite/Secure, CSRF; API and browser tests | Trusted TLS/client required; endpoint compromise defeats controls |
| Data loss from concurrent owners / P0 | OS process lease, WAL/FULL writes, failed-startup release and lease tests | Direct SDK writers must be stopped by operator |
| Derived CSV/Markdown injection / P0 fixed in Phase10 | Apostrophe formula guard and Markdown escaping; synthetic export tests | Raw exports preserve data; external spreadsheet behavior varies |
| XSS and hostile Host/Origin / P1 | Escaped UI, nonce CSP, origin/Host checks; real-browser injected-script regression | Inline style attributes allowed for React sizing |
| Credential stuffing / P1 | Per-IP and per-account bounded windows; Argon2 and hashing slots; recovery-window tests | Coarse proxy IP; no MFA or password blocklist |
| SQL injection, traversal, hostile files / P0 | Parameterized SQL, CSV-only parsing, strict names/body limits; filename and API tests | Trusted operator filesystem access is intentionally privileged |
| Resource exhaustion / P1 | Request caps, algorithm budgets, two jobs/identity, global queue, cgroups; quota/rejection tests | Cooperative native calls, no hostile multi-tenant SLA |
| Backup corruption/tampering / P0 | Verified inventory/hash/schema, staged swap, retained recovery journal; injected failure tests | Checksums are not authentication; plaintext backup |
| Holdout history reset / P0 | Current receipt union and conflict rejection on restore; repeated-claim test | Operator can delete/rollback all local history |
| Dependency compromise / P1 | Pinned bases/actions, hash-locked Python wheels, npm lock, advisories/SBOM/container scans | Scanners have incomplete coverage; residual advisories documented |
| Unsafe configuration/log disclosure / P1 | Fail-closed production validation; generic errors and limited JSON fields; configuration tests | Host logs/environment need OS access controls |

P1 audit gaps in the prior release included unverified deployment/backup operation,
unvalidated production settings and missing nonce CSP; Phase10 adds implementations
and explicit tests. No cross-owner authorization defect was established in the audit.
Container advisory findings are recorded separately; unresolved findings must not be
hidden behind a passing application suite.

P2: encrypted/authenticated backups, more browsers/platforms, wider load samples,
hard process isolation for native calculations and external operational alerts.
P3: multi-replica databases, public hosting automation, federated accounts and cloud
infrastructure. None is implicitly supported by this release.
