import argparse
import csv
import io
import json
import tempfile
import tracemalloc
from dataclasses import replace
from pathlib import Path
from random import Random
from time import perf_counter

from datagenome.identity import canonical
from datagenome.ingestion import Dataset, DatasetError, parse_csv
from datagenome.jobs import JobService
from datagenome.orchestration import DiagnosticConfig, orchestrate
from datagenome.planner import evaluate_plans
from datagenome.splits import SplitConfig, split
from datagenome.store import Store
from datagenome.versions import Transform, apply, reconstruct, register


def windows_memory():
    import ctypes
    import sys

    if sys.platform != "win32":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("faults", ctypes.c_ulong),
            ("peak_working_set", ctypes.c_size_t),
            ("working_set", ctypes.c_size_t),
            ("peak_paged", ctypes.c_size_t),
            ("paged", ctypes.c_size_t),
            ("peak_nonpaged", ctypes.c_size_t),
            ("nonpaged", ctypes.c_size_t),
            ("pagefile", ctypes.c_size_t),
            ("peak_pagefile", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(Counters),
        ctypes.c_ulong,
    ]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        return None
    return {
        "working_set_bytes": counters.working_set,
        "process_peak_working_set_bytes": counters.peak_working_set,
    }


def run(folder):
    outcomes = []
    for seed in (19, 47):
        for scenario in (
            "clean",
            "missing",
            "label-noise",
            "duplicates",
            "harmful-feature-removal",
            "minority-guard",
        ):
            rng = Random(seed)
            rows = []
            for i in range(100):
                y = int(i % 5 == 0) if scenario == "minority-guard" else i % 2
                rows.append(
                    (str(4 * y + rng.gauss(0, 0.8)), str(rng.random()), "batch", str(y))
                )
            columns = ("signal", "noise", "constant", "label")
            data = Dataset(columns, tuple(rows))
            manifest = split(data, SplitConfig("stratified", seed=seed), "label")
            train = manifest.partitions["train"]
            chosen = train[:3]
            if scenario == "missing":
                for record in chosen:
                    row = rows[record - 1]
                    rows[record - 1] = ("", *row[1:])
            if scenario == "label-noise":
                for record in chosen:
                    row = rows[record - 1]
                    rows[record - 1] = (*row[:-1], str(1 - int(row[-1])))
            if scenario == "duplicates":
                rows[chosen[1] - 1] = rows[chosen[0] - 1]
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
            payload = stream.getvalue().encode()
            data = parse_csv(payload)
            manifest = replace(manifest, dataset_sha256=canonical(data))
            store = Store(folder / f"{seed}-{scenario}.sqlite3")
            project = store.project("benchmark")["id"]
            source = register(store, project, payload, "label", manifest)
            diagnosis = orchestrate(
                data,
                payload,
                "label",
                manifest,
                DiagnosticConfig(
                    (
                        "profile",
                        "intelligence",
                        "leakage",
                        "labels",
                        "anomalies",
                        "valuation",
                    )
                ),
            )
            plan = Transform(constant_features=("constant",))
            if scenario == "label-noise":
                plan = Transform(
                    corrections=tuple(
                        (i, str(1 - int(rows[i - 1][-1]))) for i in chosen
                    )
                )
            elif scenario == "duplicates":
                plan = Transform(remove_duplicates=True)
            elif scenario == "harmful-feature-removal":
                plan = Transform(remove_features=("signal",))
            elif scenario == "minority-guard":
                minority = tuple(i for i in train if rows[i - 1][-1] == "1")
                plan = Transform(remove_records=minority, minimum_class_support=2)
            item = {
                "seed": seed,
                "scenario": scenario,
                "coverage": diagnosis["health"]["coverage"],
                "recommendations": len(diagnosis["recommendations"]),
                "engine_states": {
                    k: v["status"] for k, v in diagnosis["engines"].items()
                },
            }
            try:
                child = apply(store, project, source["id"], plan)
                item["reconstruction_equal"] = (
                    reconstruct(store, project, child["id"]) == child
                )
                result = evaluate_plans(
                    store, project, source["id"], [plan], authorized=True
                )
                item["accuracy_deltas"] = [
                    arm["delta"]["accuracy"] for arm in result["arms"]
                ]
                item["class_recall_deltas"] = [
                    arm["class_recall_change"] for arm in result["arms"]
                ]
                item["held_out_evaluated"] = result["held_out_evaluated"]
            except DatasetError as error:
                item["rejected"] = error.code
            service = JobService(store)
            queued = service.submit(
                project, source["id"], DiagnosticConfig(("profile",))
            )
            service.run_one()
            item["job_state"] = service.get(project, queued["id"])["state"]
            outcomes.append(item)
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        memory_before = windows_memory()
        tracemalloc.start()
        start = perf_counter()
        trials = run(Path(temporary))
        elapsed = perf_counter() - start
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    args.output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "trials": trials,
                "runtime_seconds": elapsed,
                "windows_memory_before": memory_before,
                "windows_memory_after": windows_memory(),
                "python_peak_bytes": peak,
            },
            allow_nan=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
