import pytest


@pytest.fixture(autouse=True)
def isolate_http_workspace(tmp_path, monkeypatch):
    # Each behavioral test owns a fresh local HTTP database.
    monkeypatch.setenv("DATAGENOME_STORE", str(tmp_path / "http.sqlite3"))
    # ASGI clients deliberately use these synthetic hosts. Exercise the real
    # host policy with an explicit test configuration, never a wildcard bypass.
    monkeypatch.setenv(
        "DATAGENOME_TRUSTED_HOSTS", "testserver,test,local,localhost,127.0.0.1"
    )
