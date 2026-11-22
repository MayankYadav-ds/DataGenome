"""Exercise the installed module's privileged CLI only in a temporary workspace."""

import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="datagenome-operator-drill-") as folder:
        root = Path(folder)
        common = [
            "--store",
            str(root / "store.sqlite3"),
            "--ledger",
            str(root / "ledger"),
        ]

        def command(operation, *arguments, password=None):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "datagenome",
                    "workspace",
                    operation,
                    *arguments,
                    *common,
                ],
                input=password,
                text=True,
                capture_output=True,
                check=True,
            )
            return json.loads(result.stdout)["status"]

        snapshot = str(root / "snapshot")
        statuses = [
            command(
                "create-account",
                "--username",
                "drill",
                "--password-stdin",
                password=secrets.token_urlsafe(24) + "\n",
            ),
            command("backup", "--output", snapshot),
            command("verify-backup", snapshot),
            command("restore", snapshot, "--dry-run"),
            command("restore", snapshot, "--apply"),
            command("integrity-check"),
            command("cleanup", "--dry-run"),
        ]
        assert statuses == [
            "account_created",
            "backed_up",
            "verified",
            "dry_run",
            "restored",
            "ok",
            "dry_run",
        ]
        print(
            json.dumps({"scope": "temporary synthetic workspace", "statuses": statuses})
        )


if __name__ == "__main__":
    main()
