import json

from datagenome.ingestion import parse_csv
from datagenome.intelligence import IntelligenceConfig, analyze


def test_missing_groups_conflicts_and_numeric_ranges() -> None:
    dataset = parse_csv(b"a,b,y\n1,2,x\n1,2,y\n1,2,y\n,3,x\n,,y\ninf,2,y\n")
    report = analyze(dataset, "y", IntelligenceConfig(ranges={"b": (0, 2)}))
    assert report["row_missing_counts"][5] == 2
    assert report["target_conditioned_missing"]["y"]["a"] == 1
    assert report["co_occurring_missing"] == [(("a", "b"), 1)]
    duplicates = report["duplicates"]
    assert duplicates["exact_groups"] == [[2, 3]]
    assert duplicates["conflicting_labels"] == [[1, 2, 3]]
    methods = {finding["method"] for finding in report["findings"]}
    assert {"range_violation", "mixed_numeric", "infinite_values"} <= methods
    json.dumps(report, allow_nan=False)
