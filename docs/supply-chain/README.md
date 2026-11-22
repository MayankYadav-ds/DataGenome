# Supply-chain evidence (2026-11-22)

Runtime Python advisory scan: pip-audit successfully queried its advisory source
for the 24 versions in `requirements/backend.versions.txt`; no advisories returned.
npm audit `--omit=dev` successfully returned zero runtime advisories. These results
exclude a complete development/build-tool audit and do not establish zero
vulnerabilities. CycloneDX outputs identify the Python runtime version list and npm
production graph; neither is a full OS/image SBOM or an independently attested build.

Trivy 0.76.2 scanned the actual local Linux amd64 images. The condensed report
preserves image IDs, timestamps, severity counts and all high/critical occurrences.
Raw full scanner output remains outside the repository. Counts are package/advisory
occurrences, including repeats across related OS packages, not unique CVEs.

| Image | Critical | High | Medium | Low | Unknown |
|---|---:|---:|---:|---:|---:|
| Backend | 0 | 50 | 100 | 81 | 7 |
| Frontend | 0 | 48 | 93 | 76 | 7 |
| Proxy | 0 | 2 | 14 | 4 | 1 |

The first Bookworm images reported two backend and one frontend critical
occurrences. The pinned Trixie transition removes these findings; zlib's available
security revision is explicitly installed. Unused runtime setuptools/pip and
frontend npm/npx were removed, eliminating the reported fixable high findings in
their vendored wheel/jaraco/undici/brace-expansion packages. Build stages still use
trusted packaging tools and are not described as advisory-free.

Remaining backend/frontend high findings are OS packages without a scanner-listed
fix. Many util-linux findings concern local host utilities; the service is non-root,
capability-free and does not execute uploaded programs. SQLite statements are
parameterized, with no arbitrary SQL endpoint. Those boundaries reduce exposure;
they are not a proof of non-exploitability for every advisory. The proxy reports
go-jose/v3 CVE-2026-116587 (no listed fix) and x/net CVE-2026-78661 (fixed upstream
at 0.62.0, image has 0.60.0). The configured reverse proxy does not accept JWK
administration or parse upstream HTML into a DOM; a rebuilt/patched official Caddy
image and further reachability validation remain outstanding. No blanket scanner
ignore list is used. Internet-facing readiness is not claimed.

Official Debian records reviewed:
[SQLite CVE-2025-7458](https://security-tracker.debian.org/tracker/CVE-2025-7458)
and [MiniZip CVE-2023-45853](https://security-tracker.debian.org/tracker/CVE-2023-45853).
The latter explicitly distinguishes Bookworm's unbuilt contrib code from affected
binaries. The base transition was tested rather than suppressing that finding.

Application licensing remains Apache-2.0. Dependency license metadata is not a legal
compatibility opinion; distributions include their upstream notices. npm reports
the development-only ESLint 9 line as unsupported; upgrading the lint stack is
deferred pending compatible Next tooling, without disabling lint checks.
