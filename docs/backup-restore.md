# Backup and restoration

These are **offline, OS-authorized operator commands**. Stop the backend and all
SDK/CLI evaluation writers first. The process lease refuses service overlap.
Backups contain private data and password hashes: use restricted filesystem
permissions and operator-managed encrypted storage. Backup encryption is **not
implemented**. Do not upload snapshots or receipt ledgers to GitHub.

Example native commands from the root (choose a new private destination):

```powershell
python -m datagenome workspace backup --output C:/private-backups/datagenome-snapshot
python -m datagenome workspace verify-backup C:/private-backups/datagenome-snapshot
python -m datagenome workspace restore C:/private-backups/datagenome-snapshot --dry-run
python -m datagenome workspace restore C:/private-backups/datagenome-snapshot --apply
python -m datagenome workspace integrity-check
```

Use `--store` and `--ledger` together for nondefault locations. Container commands
are the same inside an offline `docker compose run --rm --no-deps backend` with
an explicitly mounted private backup directory. Avoid root-owned output mounts
that prevent UID 10001 writing; prepare permissions before execution. Copying an
active SQLite file with generic file-copy tools is not this backup protocol.

The backup uses SQLite's backup API, strips sessions, copies bounded managed
holdout receipts and records SHA256 identities in a versioned manifest. It refuses
symlinks, unexpected ledger entries, active claim locks and oversized snapshots
(512 MiB DB bound, 10,000 receipts, 2 MB per receipt). Integrity verification checks
schema 2, SQLite structure, selected logical references, inventory and hashes.
Checksums detect accidental changes; they do **not authenticate a maliciously
replaced backup and manifest**. Authenticate and protect the backup out of band.

Restore defaults to dry-run. `--apply` verifies before swapping staged files,
revokes all sessions and marks queued/running jobs interrupted. Current receipts
are unioned with backed-up receipts; conflicting contents fail closed. Restoring
an older database cannot reset detectable consumption present in the current
ledger. Deleting or rolling back both the database and ledger outside the tool
can defeat local history; this is not a global tamper-proof evaluation registry.

Failed swaps attempt rollback. If rollback cannot finish, original files and a
bounded restore journal remain, and normal service startup refuses ownership.
Keep those files. After correcting storage access, inspect and apply recovery:

```powershell
python -m datagenome workspace recover-restore --dry-run
python -m datagenome workspace recover-restore --apply
```

The tests inject failed swaps and failed rollback, then verify original identity
and successful recovery. This is process/failure recovery evidence, not a
power-loss durability guarantee or an RPO/RTO commitment. Backups exclude proxy
CA keys, external TLS setup and operator environment files. Protect and back up
those separately if needed. A restore drill against a separate workspace is
required before relying on a particular backup.
