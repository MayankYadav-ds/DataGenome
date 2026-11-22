# Configuration

Backend settings are validated before serving. Invalid settings return a generic
configuration error without echoing their values. Production requires absolute
store/ledger paths, an explicit HTTPS public origin, secure cookies and explicit
trusted hosts without wildcards. `.env.example` contains examples, not credentials.
Native shells must set environment variables explicitly; Compose reads `.env`.

| Setting | Default / supported values |
|---|---|
| DATAGENOME_ENV | development; production |
| DATAGENOME_STORE | .datagenome/platform.sqlite3; absolute in production |
| DATAGENOME_LEDGER | .datagenome-ledger; dedicated directory, absolute in production |
| DATAGENOME_PUBLIC_ORIGIN | Required canonical HTTPS origin in production, no path/credentials/query |
| DATAGENOME_TRUSTED_HOSTS | Explicit comma-separated hosts, no wildcard; required in production |
| DATAGENOME_HTTPS | 0/1; production requires 1, sets secure cookies |
| DATAGENOME_REGISTRATION | Development 1, production 0; Compose base overrides to 1 for local setup |
| DATAGENOME_GUEST_SECONDS | 3600; range 60–3600 |
| DATAGENOME_SESSION_SECONDS | 28800; range 300–28800 |
| DATAGENOME_WORKERS | Only 1 |
| DATAGENOME_QUEUE_LIMIT | 8; range 1–8; each HTTP identity at most two active jobs |
| DATAGENOME_RETENTION_DAYS | Development unset, production 30; range 1–365 |
| DATAGENOME_LOG_LEVEL | Development WARNING, production INFO; INFO/WARNING/ERROR |
| DATAGENOME_BACKEND | Frontend only: http://127.0.0.1:8765 or production http://backend:8765 |
| DATAGENOME_HSTS | Frontend 0 by default; explicit 1 only in production HTTPS |
| DATAGENOME_STANDALONE | Build-only frontend flag 1 in Docker, unset for native npm start |

Host/port bindings are Uvicorn/Next CLI options; the Compose support envelope fixes
the public port to 8443. Dataset and report storage are logical SQLite artifacts,
not separate file directories. Allowed origins derive from the single public
origin; there is no permissive CORS switch. Upload, row, feature and algorithm
limits retain the bounded application contracts, rather than configurable unsafe
unlimited modes. Diagnostics permit at most 120 seconds of cooperative work;
native calls are not hard-preempted. Read [operations](operations.md).

Never put secrets in NEXT_PUBLIC variables. Session keys are random opaque tokens
stored only as hashes server-side; no shared application secret is required.
Configuration must be consistent between proxy, frontend and backend. Private
network custom origins need separate validation; they are not tested by changing
one environment variable alone.
