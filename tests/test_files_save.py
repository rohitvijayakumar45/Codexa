"""The Codebase editor's save endpoint (backend/files/api.py `/files/save`)."""

from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.files.api as files_api


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(files_api, "DATA_DIR", tmp_path)
    repo = tmp_path / "repos" / "demo"
    repo.mkdir(parents=True)
    saved: list[str] = []
    app = FastAPI()
    app.include_router(files_api.create_files_router(on_saved=saved.append))
    return repo, TestClient(app), saved


def _save(client, **body):
    return client.post("/files/save", json={"repository": "demo", **body})


def test_read_returns_the_sha_of_the_bytes_on_disk(env):
    repo, client, _ = env
    (repo / "a.py").write_bytes(b"x = 1\n")
    body = client.get("/files/read", params={"repository": "demo", "path": "a.py"}).json()
    assert body["sha"] == _sha(b"x = 1\n")


def test_save_with_the_current_sha_writes_and_reindexes(env):
    repo, client, saved = env
    (repo / "a.py").write_bytes(b"x = 1\n")
    res = _save(client, path="a.py", content="x = 2\n", base_sha=_sha(b"x = 1\n"))
    assert res.status_code == 200
    assert (repo / "a.py").read_bytes() == b"x = 2\n"
    assert res.json()["sha"] == _sha(b"x = 2\n")
    assert saved == ["demo"]


def test_a_stale_sha_is_a_conflict_and_leaves_the_file_alone(env):
    repo, client, saved = env
    (repo / "a.py").write_bytes(b"agent wrote this\n")
    res = _save(client, path="a.py", content="mine\n", base_sha=_sha(b"what I opened\n"))
    assert res.status_code == 409
    assert "changed on disk" in res.json()["detail"]
    assert (repo / "a.py").read_bytes() == b"agent wrote this\n"
    assert saved == []


def test_force_overwrites_after_a_conflict(env):
    repo, client, _ = env
    (repo / "a.py").write_bytes(b"agent wrote this\n")
    res = _save(client, path="a.py", content="mine\n", base_sha="stale", force=True)
    assert res.status_code == 200 and (repo / "a.py").read_bytes() == b"mine\n"


def test_crlf_files_keep_their_line_endings(env):
    repo, client, _ = env
    (repo / "win.txt").write_bytes(b"one\r\ntwo\r\n")
    res = _save(client, path="win.txt", content="one\nTWO\n", base_sha=_sha(b"one\r\ntwo\r\n"))
    assert res.status_code == 200
    assert (repo / "win.txt").read_bytes() == b"one\r\nTWO\r\n"


def test_a_new_file_can_be_created(env):
    repo, client, _ = env
    res = _save(client, path="src/new.ts", content="export {};\n", base_sha=None)
    assert res.status_code == 200 and (repo / "src" / "new.ts").read_text(encoding="utf-8") == "export {};\n"


def test_codexa_os_is_read_only_here(env):
    _, client, saved = env
    res = client.post("/files/save", json={"repository": "codexa-os", "path": "README.md", "content": "x"})
    assert res.status_code == 403 and saved == []


@pytest.mark.parametrize("path", ["../escape.txt", "../../etc/passwd"])
def test_paths_cannot_escape_the_repository(env, path):
    _, client, _ = env
    assert _save(client, path=path, content="x").status_code == 400


def test_binary_files_are_refused(env):
    repo, client, _ = env
    (repo / "img.bin").write_bytes(b"\x89PNG\x00\x00\x01")
    res = _save(client, path="img.bin", content="text", base_sha=_sha(b"\x89PNG\x00\x00\x01"))
    assert res.status_code == 400 and "binary" in res.json()["detail"]


def test_a_folder_is_not_a_file(env):
    repo, client, _ = env
    (repo / "src").mkdir()
    assert _save(client, path="src", content="x").status_code == 400
