import pytest

from datagenome.identity import canonical
from datagenome.independent import freeze_removal, score_frozen
from datagenome.ingestion import Dataset, DatasetError
from datagenome.modeling import ModelConfig
from datagenome.splits import Manifest, SplitConfig
from datagenome.valuation import ValuationConfig


def test_protocol_freezes_selection_and_claims_holdout_once(tmp_path):
    data = Dataset(("x", "label"), tuple((str(i), str(i % 2)) for i in range(40)))
    parts = {
        "train": list(range(1, 25)),
        "validation": list(range(25, 33)),
        "test": list(range(33, 41)),
    }
    manifest = Manifest(canonical(data), SplitConfig(), parts)
    path = tmp_path / "protocol.json"
    frozen = freeze_removal(
        data,
        "label",
        manifest,
        ValuationConfig(method="knn-shapley"),
        ModelConfig(),
        0.2,
        path,
    )
    changed = Dataset(
        data.columns,
        data.rows[:32]
        + tuple((row[0], str(1 - int(row[1]))) for row in data.rows[32:]),
    )
    changed_manifest = Manifest(canonical(changed), manifest.config, parts)
    control = freeze_removal(
        changed,
        "label",
        changed_manifest,
        ValuationConfig(method="knn-shapley"),
        ModelConfig(),
        0.2,
        tmp_path / "control.json",
    )
    assert frozen["plan"]["arms"] == control["plan"]["arms"]
    assert not frozen["exploratory"]["held_out_evaluated"]
    with pytest.raises(DatasetError, match="invalid or does not match"):
        score_frozen(changed, path, tmp_path / "ledger")
    result = score_frozen(data, path, tmp_path / "ledger")
    assert result["held_out_scored"]
    assert set(result["arms"]) == set(frozen["plan"]["arms"])
    with pytest.raises(DatasetError, match="already claimed"):
        score_frozen(data, path, tmp_path / "ledger")
