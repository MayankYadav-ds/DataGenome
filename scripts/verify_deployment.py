"""Authorized localhost-only load/restart probe using an isolated Compose project."""

import argparse
import json
import secrets
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="datagenome-phase10")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.project.startswith("datagenome-phase10") or not all(
        c.isalnum() or c == "-" for c in args.project
    ):
        parser.error("Only isolated Phase10 verification projects are permitted.")
    base = "https://localhost:8443"
    result = {
        "scope": "Synthetic local Compose verification only; local CA verification disabled in this probe, never a public TLS trust claim.",
        "base": base,
        "loads": [],
    }
    with httpx.Client(
        base_url=base, verify=False, trust_env=False, timeout=170
    ) as client:

        def timed(path):
            start = time.perf_counter()
            response = client.get(path)
            return response.status_code, time.perf_counter() - start

        for concurrency in (1, 2, 5):
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                measurements = list(
                    pool.map(lambda _: timed("/api/v1/capabilities"), range(30))
                )
            seconds = [s for _, s in measurements]
            result["loads"].append(
                {
                    "clients": concurrency,
                    "requests": len(seconds),
                    "median_seconds": median(seconds),
                    "p95_nearest_rank_seconds": sorted(seconds)[28],
                    "errors": sum(code != 200 for code, _ in measurements),
                    "requests_per_second": len(seconds) / (time.perf_counter() - start),
                    "p95_limit": "Only 30 observations; exploratory latency estimate, not an SLA.",
                }
            )
        password = secrets.token_urlsafe(24)
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "phase10_" + secrets.token_hex(6), "password": password},
        )
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        start = time.perf_counter()
        demo = client.post(
            "/api/v1/datasets/demo", json={"name": "Phase10 verification fixture"}
        )
        demo.raise_for_status()
        result["demo_registration_seconds"] = time.perf_counter() - start
        project = demo.json()["project"]["id"]
        version = demo.json()["version"]["id"]
        registered = client.get(
            f"/api/v1/datasets/{version}", params={"project_id": project}
        )
        registered.raise_for_status()
        identity = registered.json()["canonical_sha256"]
        # Strongly bounded synthetic work leaves enough time to observe a running
        # job before an authorized SIGKILL of this verification backend only.
        rows = [
            ",".join(
                [*(str(((i * (j + 3)) % 997) / 997) for j in range(32)), str(i % 2)]
            )
            for i in range(4000)
        ]
        csv = (
            ",".join([*(f"x{j}" for j in range(32)), "label"]) + "\n" + "\n".join(rows)
        )
        start = time.perf_counter()
        uploaded = client.post(
            "/api/v1/datasets",
            json={
                "project_id": project,
                "csv": csv,
                "target": "label",
                "strategy": "stratified",
                "seed": 11,
            },
        )
        uploaded.raise_for_status()
        result["upload_seconds"] = time.perf_counter() - start
        heavy = uploaded.json()["id"]
        submitted = client.post(
            "/api/v1/analyses",
            json={
                "project_id": project,
                "version_id": heavy,
                "engines": ["intelligence", "labels", "anomalies"],
                "seconds": 120,
            },
        )
        submitted.raise_for_status()
        identifier = submitted.json()["id"]
        observed = None
        for _ in range(60):
            state = client.get(
                f"/api/v1/jobs/{identifier}", params={"project_id": project}
            ).json()["state"]
            if state == "running":
                observed = state
                break
            if state not in {"queued", "running"}:
                break
            time.sleep(0.05)
        result["running_observed_before_crash"] = observed == "running"
        start = time.perf_counter()
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                args.project,
                "kill",
                "-s",
                "SIGKILL",
                "backend",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["docker", "compose", "-p", args.project, "start", "backend"],
            check=True,
            capture_output=True,
        )
        ready = False
        for _ in range(80):
            try:
                ready = client.get("/api/v1/capabilities").status_code == 200
            except httpx.TransportError:
                pass
            if ready:
                break
            time.sleep(0.25)
        result["observed_backend_recovery_seconds"] = time.perf_counter() - start
        result["backend_available_after_restart"] = ready
        state = client.get(
            f"/api/v1/jobs/{identifier}", params={"project_id": project}
        ).json()["state"]
        result["job_state_after_restart"] = state
        result["persistent_dataset_identity_unchanged"] = (
            client.get(
                f"/api/v1/datasets/{version}", params={"project_id": project}
            ).json()["canonical_sha256"]
            == identity
        )
        start = time.perf_counter()
        response = client.post(
            "/api/v1/analyses",
            json={"project_id": project, "version_id": version, "engines": ["profile"]},
        )
        response.raise_for_status()
        job = response.json()
        queued = time.perf_counter()
        for _ in range(100):
            job = client.get(
                f"/api/v1/jobs/{job['id']}", params={"project_id": project}
            ).json()
            if job["state"] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(0.05)
        result["small_diagnostic_end_to_end_seconds"] = time.perf_counter() - start
        result["post_restart_job_state"] = job["state"]
        result["queue_to_terminal_upper_bound_seconds"] = time.perf_counter() - queued
        if job["state"] == "completed":
            start = time.perf_counter()
            exported = client.get(
                f"/api/v1/reports/{job['result_id']}",
                params={"project_id": project, "format": "json", "privacy": "summary"},
            )
            result["export_seconds"] = time.perf_counter() - start
            result["export_status"] = exported.status_code
        result["memory_scope"] = (
            "Current container activation cgroup peak and current backend process VmHWM, sampled after restart verification. Not the killed process peak and not a full-run peak. Shared-page accounting differs between process RSS and cgroup memory."
        )
        memory_script = "import glob,json; out={};\nfor p in glob.glob('/proc/[0-9]*/cmdline'):\n try:\n  a=open(p,'rb').read().split(b'\\0');\n  if b'uvicorn' in a:\n   fields=dict(line.split(':',1) for line in open(p.replace('cmdline','status')) if ':' in line); out={'process_peak_working_set':fields.get('VmHWM','unavailable').strip(),'process_current_rss':fields.get('VmRSS','unavailable').strip()}\n except OSError: pass\ntry: out['container_memory_peak_bytes']=int(open('/sys/fs/cgroup/memory.peak').read())\nexcept OSError: pass\nprint(json.dumps(out))"
        memory = subprocess.check_output(
            [
                "docker",
                "compose",
                "-p",
                args.project,
                "exec",
                "-T",
                "backend",
                "python",
                "-c",
                memory_script,
            ],
            text=True,
        )
        result["memory"] = json.loads(memory)
        result["status"] = (
            "pass"
            if ready
            and state == "interrupted"
            and result["persistent_dataset_identity_unchanged"]
            and job["state"] == "completed"
            else "partial"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, allow_nan=False)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
