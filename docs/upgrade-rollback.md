# Upgrade and rollback

0.7.0 retains schema 2. Store accepts schema 0/1/2 and refuses unknown schemas.
That acceptance is not a guarantee that an older release understands new artifacts.
No irreversible schema migration is introduced in Phase 10.

1. Record the current commit/image digest and configuration; stop the service and
   all direct evaluation writers.
2. Create and verify an offline backup, including the holdout ledger. Keep it on
   restricted storage and perform a restore drill into a separate workspace.
3. Build/install the intended version, preserving named workspace volumes.
4. Run integrity-check and doctor. Start exactly one backend, check readiness,
   authenticate and inspect existing datasets and job states.
5. Keep the prior image and verified backup until acceptance.

For rollback, stop the new version first. If no data changed, restart the retained
old version only if its artifact/schema compatibility is known. Otherwise restore
the verified compatible snapshot with the offline restore workflow. Preserve current
holdout receipts: their union must not erase evaluations performed since backup.
Restoration discards post-backup application changes and revokes sessions. Obtain
the operator's explicit acceptance of that data loss before applying it to real data.

Do not force-push Git history or remove volumes as a rollback mechanism. Cross-version
rollback across future irreversible migrations is **NOT VERIFIED**. The tests verify
same-schema restoration and failure rollback, not every historical release pair.
