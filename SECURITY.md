# Security

For 0.7.0, read the [security model](docs/security-model.md),
[threat model](docs/threat-model.md), [advisory evidence](docs/supply-chain/README.md)
and [production limitations](docs/production-limitations.md). Supported deployment is
operator-controlled and loopback-bound; public internet security is not verified.
Backups contain private data and password hashes and are not encrypted by this tool.

If private GitHub vulnerability reporting is enabled, use the repository's Security tab
to report a suspected vulnerability. Include the affected version and a synthetic
example. Keep credentials and private datasets out of issue trackers and reports.

The 0.4 local authentication, ownership, storage and deployment boundaries are
documented in [docs/security.md](docs/security.md). This is not a certification
for internet-facing hosting. Keep the server bound to loopback.
