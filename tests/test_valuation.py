import asyncio
import json
import subprocess
import sys
from itertools import permutations

import pytest
from auth_helpers import authenticate_async
from httpx import ASGITransport, AsyncClient

from datagenome.api import create_app
from datagenome.identity import canonical
from datagenome.ingestion import Dataset, DatasetError
from datagenome.modeling import ModelConfig
from datagenome.removal import compare_removal
from datagenome.splits import Manifest, SplitConfig
from datagenome.valuation import ValuationConfig, value_data
from datagenome.valuation_math import exact_values, knn_values, sampled_values


def test_exact_shapley_axioms_and_banzhaf_reference():
    def coalition(mask):
        return float((mask & 3) == 3)

    def additive(mask):
        return float((mask & 4) != 0)

    phi = exact_values(4, coalition)
    assert phi == pytest.approx([0.5, 0.5, 0, 0])
    assert sum(phi) == pytest.approx(coalition(15) - coalition(0))
    assert exact_values(
        4, lambda mask: coalition(mask) + additive(mask)
    ) == pytest.approx([0.5, 0.5, 1, 0])
    # For a three-way unanimity game each Banzhaf marginal occurs in one of four coalitions.
    assert exact_values(
        3, lambda mask: float(mask == 7), banzhaf=True
    ) == pytest.approx([0.25] * 3)
    result, variability, history = sampled_values(4, coalition, 42, 128)
    assert result == pytest.approx(phi, abs=0.15)
    assert sum(result) == pytest.approx(1)
    assert variability[2:] == [0, 0]
    assert history[-1]["permutations"] == 128


def test_knn_recurrence_matches_exhaustive_permutations_with_ties():
    x, y = [[0.0], [0.0], [2.0], [3.0]], ["a", "b", "a", "b"]
    for k in (1, 2, 4):
        expected = [0.0] * 4
        for ordering in permutations(range(4)):
            ids = []
            old = 0.0
            for index in ordering:
                ids.append(index)
                ranked = sorted(ids, key=lambda i: (x[i][0] ** 2, i))
                new = sum(y[i] == "a" for i in ranked[:k]) / k
                expected[index] += (new - old) / 24
                old = new
        assert knn_values(x, [[0.0]], y, ["a"], k, lambda: None) == pytest.approx(
            expected
        )


def dataset_and_manifest(n=6):
    data = Dataset(
        ("x", "constant", "label"),
        tuple((str(i), "1", "a" if i % 2 else "b") for i in range(n + 6)),
    )
    split = {
        "train": list(range(1, n + 1)),
        "validation": list(range(n + 1, n + 5)),
        "test": [n + 5, n + 6],
    }
    return data, Manifest(canonical(data), SplitConfig(), split)


@pytest.mark.parametrize(
    "method", ["loo", "shapley", "mc-shapley", "knn-shapley", "banzhaf"]
)
def test_valuation_methods_preserve_source_and_ignore_heldout(method):
    data, manifest = dataset_and_manifest()
    config = ValuationConfig(method=method)
    initial = value_data(data, "label", manifest, config)
    changed = Dataset(data.columns, data.rows[:-2] + (("bad", "1", "new"),) * 2)
    result = value_data(
        changed,
        "label",
        Manifest(canonical(changed), manifest.config, manifest.partitions),
        config,
    )
    assert initial["records"] == result["records"]
    assert initial["dataset_sha256"] == canonical(data)
    assert {row["record_id"] for row in result["records"]} == set(
        manifest.partitions["train"]
    )
    if method in {"shapley", "mc-shapley", "knn-shapley"}:
        assert sum(row["score"] for row in result["records"]) == pytest.approx(
            result["full_utility"] - result["empty_utility"]
        )
    if method == "loo":
        assert result["utility_evaluations"] == 7


def test_budget_metric_and_contamination_checks():
    data, manifest = dataset_and_manifest()
    with pytest.raises(DatasetError, match="Budget"):
        value_data(
            data,
            "label",
            manifest,
            ValuationConfig(method="shapley", max_evaluations=3),
        )
    with pytest.raises(DatasetError, match="explicit"):
        value_data(data, "label", manifest, ValuationConfig(metric="class_recall"))
    changed = Dataset(data.columns, data.rows[:6] + (data.rows[0],) + data.rows[7:])
    with pytest.raises(DatasetError, match="exact feature"):
        value_data(
            changed,
            "label",
            Manifest(canonical(changed), manifest.config, manifest.partitions),
        )


def test_removal_counts_and_class_caps():
    data, manifest = dataset_and_manifest(20)
    result = compare_removal(
        data,
        "label",
        manifest,
        ValuationConfig(method="knn-shapley"),
        ModelConfig(),
        0.2,
    )
    assert not result["held_out_evaluated"]
    for name in ("lowest", "highest", "random"):
        ids = result["arms"][name]["removed_ids"]
        assert len(ids) == 4
        assert sum(data.rows[i - 1][-1] == "a" for i in ids) == 2


def test_valuation_cli_and_api(tmp_path):
    payload = b"x,label\n" + b"".join(f"{i},{i % 2}\n".encode() for i in range(12))
    path = tmp_path / "data.csv"
    path.write_bytes(payload)
    result = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                "-m",
                "datagenome",
                "value-data",
                str(path),
                "--target",
                "label",
                "--method",
                "knn-shapley",
            ]
        )
    )
    assert result["valuation"]["records"]

    async def run():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            await authenticate_async(client)
            url = "/api/v1/datasets/valuation?filename=data.csv&target=label&method=knn-shapley"
            response = await client.post(
                url, content=payload, headers={"content-type": "text/csv"}
            )
            assert response.status_code == 200, response.text
            assert (
                response.json()["valuation"]["records"]
                == result["valuation"]["records"]
            )

    asyncio.run(run())
