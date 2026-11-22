# Security model

DataGenome trusts the host administrator, installed code and filesystem permissions.
Direct Python SDK/operator commands have trusted local access; HTTP callers do not.
The supported service is one loopback-bound instance. No formal security certification
or independent penetration test is claimed. See the [threat model](threat-model.md).

Accounts use Argon2id (time 3, 65536 KiB, parallelism 1) with library-generated salts
and at most two concurrent hashing operations. Authentication uses random opaque
session tokens, hashed server-side, HttpOnly/SameSite cookies, CSRF checks and bounded
expiry. Production cookies require Secure. Successful identity changes revoke the
presented prior session and rotate credentials. Logout/expiration revoke access.
Production registration defaults off. Recovery, email verification, MFA and breached
password screening are unavailable; there is no fake recovery action.

Project ownership is enforced server-side, including jobs, indirect version references,
reports, downloads, deletion and experiments. Tests use two accounts and two guests,
cross-owner identifiers and every protected API operation without a session. Ownership
checks supplement parameterized SQL and strict request contracts. The frontend remains
an untrusted client, even though it also clears identity-scoped state across tabs.

Nonce CSP protects scripts in production; unsafe-eval is restricted to development.
`style-src-attr 'unsafe-inline'` remains necessary for trusted React dynamic sizing;
it is not a script relaxation. HTML is escaped by React. Derived report CSV cells
with formula prefixes are quoted with an apostrophe; Markdown metacharacters/HTML
are escaped. Original dataset exports preserve original bytes/values and are offered
as a `.csv.txt` attachment: inspect before deliberately opening in a spreadsheet.
No spreadsheet sanitizer can guarantee safety in every application/import workflow.

Guidance reviewed against official sources: [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html),
[Caddy local HTTPS](https://caddyserver.com/docs/automatic-https), and
[SQLite online backup](https://www.sqlite.org/backup.html).
These inform individual controls; NIST conformance is not claimed.
