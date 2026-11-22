# Production limitations

The support envelope is one trusted host/operator, one backend and one SQLite
workspace, loopback HTTP native or loopback HTTPS Linux amd64 Compose. This is
0.7.0, not v1.0. Public internet security is **NOT VERIFIED**. Private-network remote
clients, public certificate issuance, macOS, ARM64 and distributed operation are
**NOT RUN** unless separately stated in the verification report.

Backups are plaintext, bounded and checksum-verified, not cryptographically
authenticated. Operator privileges can access all stored records and reset local
history outside supported commands. Snapshots exclude proxy CA keys/config secrets.
Process-crash recovery is tested; power-loss safety and formal RPO/RTO are not.
There is no filesystem encryption, MFA, email verification or account recovery.

Resource limits are bounded local safeguards, not immunity to denial of service.
Jobs use cooperative cancellation; native calculations cannot always stop promptly.
SQLite storage growth requires host monitoring; ten-client load and enterprise
scale are not established. Advisories and SBOMs are point-in-time evidence.

Scientific validation remains **PARTIAL**. The 357 Phase9 records and unfavorable
Digits intervention results remain unchanged. Deployment work does not validate
scientific accuracy, causal influence, fairness, universal label-error detection
or intervention benefit. Training/validation/test separation and ledger safeguards
retain their existing limitations documented in `research/threats-to-validity.md`.
