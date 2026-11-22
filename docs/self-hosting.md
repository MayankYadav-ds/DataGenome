# Self-hosting

Prerequisites: Python 3.11, Node 24, or Docker with Compose and Linux amd64
containers. The tested container budgets total 2.9 GiB plus Docker/build overhead;
allow additional host memory and disk space. Builds need registry access.

## Native Windows, loopback HTTP

From the repository root, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install ".[api,dev]"
python -m datagenome --help
python -m uvicorn datagenome.api:app --host 127.0.0.1 --port 8765 --workers 1 --no-access-log
```

In another terminal at the root:

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend start -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000. Stop both foreground processes with Ctrl+C.
Development uses non-secure cookies on loopback HTTP. Windows Application Control
prevented the installed scikit-learn 1.9.1 native module from loading on the
verification machine; the verified local environment uses 1.6.1. Do not disable
OS controls. The container lock also uses 1.6.1.

## Compose, local HTTPS

```powershell
docker compose up -d --build --wait
docker compose ps
docker compose exec backend python -m datagenome doctor
docker compose stop
```

Open https://localhost:8443. Caddy uses a private local CA, not a publicly trusted
certificate. Automated verification explicitly ignores this local certificate's
trust error; that does not verify public TLS trust. No host trust store is changed.
For human use, independently inspect and explicitly trust the local CA certificate
using your OS/browser's documented procedure; never distribute its private key.
HSTS is off by default. The included Caddy configuration supports localhost only.
Other private-network hostnames and remote client trust are **NOT VERIFIED**.

The initial loopback stack enables registration for setup. For closed registration,
stop the backend and provision accounts through the offline operator command:

```powershell
docker compose stop backend
docker compose run --rm --no-deps backend python -m datagenome workspace create-account --username operator
docker compose -f compose.yaml -f compose.production.yaml up -d --wait
```

The account command prompts without echoing a password. It is privileged by access
to the workspace volume, not an HTTP administration endpoint. It creates no session.
The production override disables registration and enables restart-unless-stopped.
Guests remain available and resource bounded; this is not a hostile multi-tenant
service. See [configuration](configuration.md) and [limitations](production-limitations.md).

`docker compose down` retains named volumes. **Do not use `down -v` for a workspace
you need to keep.** Stop the backend before offline backup/restore and upgrades.
Do not publish backend/frontend ports or change the binding to all interfaces as
part of this supported configuration.
