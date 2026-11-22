# Phase 10 — 0.7.0 self-hosting hardening

Starting checkpoint: `08e0861b5d18030a061313c4f4914553a11ab812` on public main.
Its remote SHA and successful Windows run 44476707246 were independently checked.
The initial working tree was clean. Version 0.7.0 is a self-hosted preview, not v1.0.
Implementation commit: `47bf7e8a59378e0206510f9d5cb2c39420b640fc`, pushed to public main using the existing GitHub noreply identity.
[Hosted run 44989000650](https://github.com/MayankYadav-ds/DataGenome/actions/runs/44989000650)
completed successfully on 2026-11-22: Windows/Linux installed-wheel checks, Windows
Chromium, Linux Firefox, Linux WebKit, the actual Compose browser job and runtime
advisory auditing (seven jobs). Browser jobs run all eight workflows plus the sign-in
regression in separate/paced cohorts. Linux WebKit is not a Safari certification.

## Implemented and verified locally

- Validated production settings; strict public/internal hosts and origin boundaries.
- Session rotation/revocation, account login throttling, existing Argon2id hashing,
  owner and guest isolation, queue limits and one-process workspace ownership.
- Nonce CSP, forged-host/origin rejection, safe derived report exports, filename
  validation, and a corrected guest identity/focus reconciliation race.
- Actual non-root backend/frontend/proxy images, persistent volumes, internal
  networks, bounded resources and localhost-only HTTPS. Linux amd64 only.
- Offline SQLite/ledger backups, inventory/hash/schema verification, staged restore,
  receipt union, session invalidation and explicit recovery after failed rollback.
- Liveness/readiness, bounded structured request/security logs, offline operator
  commands and persisted interrupted-job recovery.
- Cross-platform/browser/container CI definitions and point-in-time advisories/SBOMs.

## Local verification

| Capability | Result and scope |
|---|---|
| Windows installed-wheel backend | PASS: 134 tests; pip check; Ruff lint/format; strict mypy, 58 source modules |
| Packaging | PASS: wheel and source distribution builds; module CLI exercised |
| Linux amd64 operator/security tests | PASS: 20 production tests in isolated wheel-installed test container |
| Frontend | PASS: 20 unit tests, TypeScript, ESLint, formatting and production build |
| Windows Chromium | PASS: eight workflows plus the focused sign-in regression, verified separately to respect source-IP budgets |
| HTTPS container Chromium | PASS in paced cohorts: eight workflows plus one sign-in regression. An earlier combined run passed all nine; a final combined burst hit HTTP 429 (eight passed). Limits/assertions are unchanged |
| Windows Firefox | BLOCKED: browser launch `spawn UNKNOWN`; exact OS cause unverified, no controls bypassed |
| Windows WebKit | PARTIAL: seven of eight scenarios; Tab did not focus the skip link even after bringing the page forward; no Safari claim |
| Authentication/authorization/guests | PASS in regression scope: two accounts/two guests, revoked sessions, cross-owner resources and every protected operation without a session |
| Backup/restore/recovery | PASS Windows and Linux tests; actual installed CLI and offline Compose restore drills also passed |
| Closed registration | PASS: production override rejected registration with 403; restored operator account login/session returned 200; [record](deployment-operator-verification.json) |
| Persistence/job restart | PASS: SIGKILL of isolated backend, interrupted state, unchanged dataset identity, new job/export afterward |
| HTTPS | PASS only for local encrypted transport with a private Caddy CA; automated clients explicitly skip local CA trust verification |
| Dependency auditing | PARTIAL: runtime Python/npm no returned advisories; container high findings remain, no critical findings in final scans |
| Public internet, remote private network, ARM64, macOS | NOT VERIFIED / NOT RUN |

See [measured performance](performance.md), [advisory details](supply-chain/README.md),
[risk inventory](threat-model.md), [operations](operations.md), [configuration](configuration.md),
[deployment](deployment.md), [native/Compose startup](self-hosting.md),
[backup/restore](backup-restore.md), [upgrade/rollback](upgrade-rollback.md) and
[remaining limits](production-limitations.md).

Checkpoints 10A–10Z are addressed within those explicit scopes, not universally
completed. Remaining work includes proxy advisory remediation, full license/build
dependency review, remote trusted TLS, native WebKit keyboard behavior and Firefox
launch diagnosis, additional operational metrics and optional backup encryption.
Unmeasured performance categories are listed rather than fabricated. Hosted Linux,
Windows, browser and container jobs passed in the linked implementation run.
The Windows-specific Firefox launch and WebKit keyboard differences remain open.

The 357 Phase9 scientific records remain unchanged, including neutral/adverse
Digits intervention outcomes. Scientific validation remains **PARTIAL**. No original
datasets were automatically modified. No unrelated repository, visibility, ownership
or access settings were changed. No external deployment or paid service was used.
Expenditure: **₹0**. Phase11 is not started.

LOCAL APPLICATION READINESS: PASS within the tested Chromium/Windows scope.

CONTAINER DEPLOYMENT READINESS: PASS within the localhost Linux amd64 scope.

SUPPORTED SELF-HOSTED PRODUCTION READINESS: PARTIAL; residual advisories and the
explicit operational/security limitations remain.

PUBLIC INTERNET PRODUCTION READINESS: NOT VERIFIED.
