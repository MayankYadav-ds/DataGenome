import pytest


@pytest.fixture(autouse=True)
def isolate_http_workspace(tmp_path, monkeypatch):
    # Each behavioral test owns a fresh local HTTP database.
    monkeypatch.setenv("DATAGENOME_STORE", str(tmp_path / "http.sqlite3"))
