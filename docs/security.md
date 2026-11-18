# Authentication, authorization and privacy

DataGenome 0.4 is a **local, one-process application**, not a verified public
multi-tenant deployment. Bind Uvicorn to loopback. The SQLite file, local account,
OS administrator and trusted direct SDK/CLI callers remain inside the trust boundary.
Do not expose the service publicly merely because these checks pass.

## Identity and requests

Register/login use Argon2id through argon2-cffi (MIT; bindings include Apache-2.0
components). Passwords have 12–256 characters and are never persisted in cleartext.
Usernames are case-insensitive local identifiers, not email addresses. Registration
can be disabled with `DATAGENOME_REGISTRATION=0`. Email verification and recovery
are unavailable. Rehash-on-login and account password changes are deferred.

Server-side sessions last eight hours for accounts and one hour for guests.
Cryptographically random session tokens are stored as SHA-256 digests, alongside
CSRF token digests. Logout and deletion revoke them. Cookies are HttpOnly and
SameSite strict. Loopback HTTP development omits Secure; set `DATAGENOME_HTTPS=1`
only with HTTPS. Password hashing intentionally consumes CPU/memory; local rate
limits are conservative protection, not distributed denial-of-service resistance.

Create a session with POST `/api/v1/auth/guest`, `/register`, or `/login`.
The response contains `csrf_token`; send it as `X-CSRF-Token` on every authenticated
mutation. Cookies authenticate all `/api/v1` routes except capabilities and the
three session-creation routes. GET `/auth/csrf` rotates the CSRF token after reload.
GET `/auth/session` returns the current local identity. Cross-origin browser
requests are rejected; no permissive CORS is installed. Registration/login require
JSON. Non-browser callers must handle cookies and CSRF too. No bearer API keys.

## Ownership and migration

Every persistent lookup verifies project ownership in SQLite, including indirect
job, report, experiment, recommendation, preprocessing and version access. Wrong
ownership returns 404 without exposing object existence. New HTTP projects receive
an owner atomically. UUIDs are not an authorization mechanism. There is no sharing
or collaborator API. Two accounts, two guests, and guest/account access are tested.

Schema 1 upgrades to 2, adding ownership metadata. **Existing projects remain
unowned and inaccessible over HTTP.** There is no automatic adoption. Trusted
local SDK/CLI calls can still access local projects. Re-upload reviewed data to
create a new owned project. Back up before migration; there is no downgrade tool.
This does not alter GitHub repository ownership or collaborators.

## Guests and lifecycle

Guests can immediately create a synthetic demo, upload, analyze, review experiments,
and export reports. Limits: three projects, 500 rows/32 columns per uploaded dataset,
30-second cooperative job budgets and at most three model fits per experiment.
Accounts allow 50 projects and 5,000 rows/64 columns. All requests have byte limits;
the global queue allows eight active jobs and one worker. Projects allow 1,000
artifacts/jobs; experiments reserve artifact headroom. Rate limits include 240
requests/minute per direct client IP, 10 login attempts/5 minutes, 20 guest sessions
and 20 registrations/hour. These may reject polling bursts; slow down on 429.
Do not trust forwarded IP headers. Limits are single application database limits.

Expired guests are cleaned on startup, new guest creation, and every 60 seconds.
Explicit DELETE `/auth/account` revokes sessions and removes the owner's resources.
Running computations first receive cancellation; a 202 means deletion awaits the
cooperative boundary and next cleanup. Account deletion pending cleanup is marked
expired; other accounts are unaffected. Guest-to-account merging is unsupported.

DELETE project removes its jobs, events, artifacts and ownership. Running jobs
must stop first (409); queued jobs are removed atomically. DELETE dataset removes
its entire version lineage and conservatively clears all derived results/jobs in
that project, while retaining other dataset versions. Explain this scope before
confirmation in the frontend. DELETE report removes the persisted analysis, but
not independently cached diagnostics. Set `DATAGENOME_RETENTION_DAYS=1..365` to
expire old analysis/cache/experiment-result bodies, excluding active projects;
maintenance runs every minute. Default retention is indefinite for account data.
Datasets, transformation artifacts and plans persist until explicit deletion.

SQLite writes use transactions and a ten-second busy timeout. This release requires
one application process and one worker; do not use multiple Uvicorn workers.
Restart marks running work interrupted; queued requests survive. Cancellation and
deadlines occur between native fits/engines, so wall-clock limits are not hard kills.

## Storage and deployment limits

The database contains raw datasets, identifiers, hashes, labels and detailed reports.
**There is no encryption at rest.** Keep it in a private user directory with OS ACLs
and disk encryption where available. Windows inherits the current user's directory
ACLs; the application does not independently certify or rewrite them. Do not place
it in shared/synchronized directories. Local admins and trusted SDK callers can
read it. SQLite logical deletion does not guarantee physical erasure from pages,
backups, journals or SSDs. Manage backups separately. No secure-erasure claim.

Summary reports omit raw rows, hashes, labels and record IDs. Authenticated detailed
reports and explicitly reviewed previews can contain sensitive data. Logs record
error codes, never request bodies or passwords; unexpected errors return generic
messages. Disable access logging or apply an operator-reviewed URL redaction policy
when URLs can include sensitive project identifiers. Responses set no-store,
nosniff, frame restrictions and random correlation IDs. TLS termination, trusted
host configuration, account recovery, distributed throttling, security monitoring,
independent penetration testing and hardened internet hosting remain deployment work.

Dependency advisory results cover the tested environment at scan time, not every
future version permitted by package ranges. Install maintained compatible releases
and rerun advisories before deployment. No paid infrastructure is required.
