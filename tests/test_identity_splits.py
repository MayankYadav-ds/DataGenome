from dataclasses import asdict

import pytest

from datagenome.identity import identify
from datagenome.ingestion import DatasetError, parse_csv
from datagenome.leakage import LeakageConfig, inspect_leakage
from datagenome.splits import Manifest, SplitConfig, restore, split, validate


def test_identity_normalization_and_configuration() -> None:
    left = b"x,y\n1,a\n"
    right = b'\xef\xbb\xbfx,y\r\n"1",a\r\n'
    a = identify(parse_csv(left), left, "y")
    b = identify(parse_csv(right), right, "y")
    assert a.canonical_sha256 == b.canonical_sha256
    assert a.source_sha256 != b.source_sha256
    assert a.version_id == b.version_id
    assert a.features == 1
    assert (
        identify(parse_csv(left), left, parent=a.version_id).version_id != a.version_id
    )
    altered = b"x,y\n2,a\n"
    c = identify(parse_csv(altered), altered, "y")
    assert c.schema_sha256 == a.schema_sha256
    assert c.canonical_sha256 != a.canonical_sha256


def test_split_roundtrip_and_tampering() -> None:
    data = parse_csv(b"x,y\n1,a\n2,a\n3,a\n4,b\n5,b\n6,b\n")
    config = SplitConfig(strategy="stratified")
    manifest = split(data, config, "y")
    assert manifest == split(data, config, "y")
    report = {"split": {**asdict(manifest), "fingerprint": manifest.fingerprint}}
    assert restore(report) == manifest
    invalid = Manifest(
        manifest.dataset_sha256, config, {key: [1, 2] for key in manifest.partitions}
    )
    with pytest.raises(DatasetError, match="cover every"):
        validate(data, invalid)
    with pytest.raises(DatasetError, match="three units"):
        split(parse_csv(b"x,y\n1,a\n2,a\n3,b\n"), config, "y")


def test_group_and_chronological_splits() -> None:
    data = parse_csv(b"g,t\na,2024-01-01\nb,2024-01-02\nc,2024-01-03\na,2024-01-01\n")
    for config in (
        SplitConfig("group", group="g"),
        SplitConfig("chronological", time="t"),
    ):
        manifest = split(data, config)
        assert any({1, 4} <= set(ids) for ids in manifest.partitions.values())
        validate(data, manifest)
    with pytest.raises(DatasetError, match="Incompatible"):
        split(data, SplitConfig("random", group="g"))


def test_structural_and_statistical_leakage_are_separate() -> None:
    data = parse_csv(
        b"x,c,g,t,y\n1,a,g,2024-01-08,a\n2,a,h,2024-01-08,a\n"
        b"3,a,i,2024-01-08,a\n4,b,j,2024-01-08,b\n5,b,k,2024-01-08,b\n"
        b"6,b,l,2024-01-08,b\n1,a,g,2024-01-08,a\n"
        b"8,b,h,2024-01-04,b\n9,b,m,2024-01-10,b\n"
    )
    generated = split(data, SplitConfig())
    manifest = Manifest(
        generated.dataset_sha256,
        generated.config,
        {"train": list(range(1, 7)), "validation": [7, 8], "test": [9]},
    )
    signals = inspect_leakage(
        data, "y", manifest, LeakageConfig(group="g", time="t", cutoff="2024-01-06")
    )
    categories = {item.method: item.classification for item in signals}
    assert categories["target_copy"] == "strong_statistical_evidence"
    for method in (
        "cross_split_rows",
        "cross_split_features",
        "group_overlap",
        "temporal_overlap",
        "training_after_cutoff",
    ):
        assert categories[method] == "confirmed_violation"
    assert len({item.id for item in signals}) == len(signals)


def test_shape_limits() -> None:
    with pytest.raises(DatasetError, match="row limit"):
        parse_csv(b"a\n1\n2\n", max_rows=1)
    with pytest.raises(DatasetError, match="column limit"):
        parse_csv(b"a,b\n1,2\n", max_columns=1)
