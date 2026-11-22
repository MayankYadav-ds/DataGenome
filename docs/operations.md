# Operations

`/health` is liveness; `/ready` checks database connectivity and the owning worker
thread. Both deliberately omit private paths, record counts and dataset contents.
The frontend health probe uses the configured public Host. Caddy logs operational
events; backend emits JSON request completion/rejection records with correlation
ID, status and duration. It omits raw URLs, credentials, identities and records.
Default production level is INFO. Protect log files and retention at the host.

```powershell
python -m datagenome doctor
python -m datagenome workspace integrity-check
python -m datagenome workspace cleanup --dry-run
docker compose ps
docker compose logs --tail 50 backend frontend proxy
```

Doctor validates settings, database/schema/reference integrity and managed receipts.
It does not test all installed native modules or port conflicts. A missing database
is refused rather than silently initialized. Cleanup is a nonmutating inventory;
mutating cleanup is unsupported by this command. Reviewed application retention
remains the supported deletion mechanism. Retention is not a substitute for backup.

One persisted queue and one worker serve the workspace. HTTP identities have two
active-job slots, global capacity is at most eight, requests/algorithms retain
existing size and compute guards. Login limits are per IP and hashed account key.
The frontend's internal IP collapses public client identity; IP limits are coarse
and can affect other users. Account rate limiting supplements this boundary.
Limits reduce denial-of-service risk; they do not prevent every hostile workload.

On restart, previously running jobs become interrupted; requests are not secretly
replayed as successful experiments. SQLite uses WAL, FULL synchronous writes and
a ten-second busy timeout. Storage errors in the worker are logged without data
and retried with a bounded pause. A failed readiness probe is an operational signal,
not proof of corruption. Do not delete database/WAL/journal files to fix it.

Shutdown signals cooperative cancellation. Docker allows 140 seconds, Uvicorn 130;
individual native calls may outlive cooperative checks. The lease remains held if
the worker has not stopped, until OS process exit. For a hung process, stop that
specific instance and inspect interrupted work after restart. There is no distributed
scheduler, automatic failover, external metrics collector or alert delivery service.
Use queue state and job event timestamps for operational diagnosis; no high-cardinality
public metrics containing user/project identifiers are emitted.
