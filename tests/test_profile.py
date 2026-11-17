import io
from dataclasses import asdict

import pytest

from datagenome.ingestion import DatasetError, load_csv, parse_csv
from datagenome.profiling import profile


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"", "empty_dataset"),
        (b"a,b\n\n", "empty_dataset"),
        (b"a,a\n1,2", "invalid_header"),
        (b"a, \n1,2", "invalid_header"),
        (b"a,b\n1", "malformed_csv"),
        (b"a\n1,2", "malformed_csv"),
        (b'a\n"unfinished', "malformed_csv"),
        (b"a\n\x00", "malformed_csv"),
        (b"a\n\xff", "invalid_encoding"),
    ],
)
def test_invalid_csv(payload: bytes, code: str) -> None:
    with pytest.raises(DatasetError) as caught:
        parse_csv(payload)
    assert caught.value.code == code


def test_file_validation() -> None:
    payload = b"a\n1\n"
    assert load_csv(io.BytesIO(payload), "REPORT.CSV", len(payload)).rows == (("1",),)
    with pytest.raises(DatasetError, match="byte limit"):
        load_csv(io.BytesIO(payload), "report.csv", len(payload) - 1)
    with pytest.raises(DatasetError, match="filename"):
        load_csv(io.BytesIO(payload), "report.tsv")


def test_profile_statistics() -> None:
    dataset = parse_csv(
        b"\xef\xbb\xbfamount,id,empty,flag,label\r\n1,001,,true,A\r\n"
        b'3,002, ,False,B\r\n1,001,,true,A\r\n,004,,true,"A\r\nx"\r\n'
    )
    report = profile(dataset, "label")
    assert (report.row_count, report.column_count, report.duplicate_row_count) == (
        4,
        5,
        1,
    )
    assert [column.dtype for column in report.columns] == [
        "integer",
        "string",
        "empty",
        "boolean",
        "string",
    ]
    assert report.columns[0].numeric == {
        "min": 1,
        "max": 3,
        "mean": pytest.approx(5 / 3),
        "median": 1,
    }
    assert report.columns[0].missing_percentage == 25.0
    assert report.columns[0].unique_count == 2
    assert report.target_distribution == {"A": 2, "A\r\nx": 1, "B": 1}
    findings = [asdict(item) for item in report.findings]
    assert findings[0]["affected_records"] == (3,)
    assert len({item["id"] for item in findings}) == len(findings)
    with pytest.raises(DatasetError, match="Target"):
        profile(dataset, "missing")


def test_extreme_finite_statistics() -> None:
    report = profile(parse_csv(b"value\n1.7e308\n1.7e308\n"))
    assert report.columns[0].numeric == dict.fromkeys(
        ("mean", "min", "max", "median"), 1.7e308
    )
    assert profile(parse_csv(b"value\n1e999\n")).columns[0].numeric is None


def test_all_missing_target() -> None:
    report = profile(parse_csv(b"id,label\n1,\n2, \n"), "label")
    assert report.target_distribution == {}
    assert {finding.category for finding in report.findings} == {
        "missing_values",
        "insufficient_target_classes",
    }
