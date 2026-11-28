import json
import zipfile

import pytest

from volleyball_stats import updates

SHA_A, SHA_B = "a" * 40, "b" * 40


def archive(path, sha, files):
    with zipfile.ZipFile(path, "w") as z:
        z.comment = sha.encode()
        for name, text in files.items():
            z.writestr(f"volleyball-stats-main/{name}", text)
    return path


def test_install_writes_the_code_then_an_update_removes_what_went(tmp_path):
    root = tmp_path / "app"
    first = archive(tmp_path / "1.zip", SHA_A, {"pyproject.toml": "a", "src/old.py": "x", "src/kept.py": "1"})
    assert updates.install(root, first) == SHA_A
    (root / "outputs").mkdir()
    (root / "outputs/match.json").write_text("mine", encoding="utf-8")

    second = archive(tmp_path / "2.zip", SHA_B, {"pyproject.toml": "b", "src/kept.py": "2", "src/new/one.py": "n"})
    assert updates.install(root, second) == SHA_B

    assert not (root / "src/old.py").exists()
    assert (root / "src/kept.py").read_text(encoding="utf-8") == "2"
    assert (root / "src/new/one.py").exists()
    assert (root / "outputs/match.json").read_text(encoding="utf-8") == "mine"
    assert updates.commit(root) == SHA_B
    assert json.loads((root / updates.INSTALLED).read_text(encoding="utf-8"))["files"] == ["pyproject.toml", "src/kept.py", "src/new/one.py"]
    assert not list(root.glob(".update-*"))


def test_install_refuses_a_git_checkout_and_a_file_out_of_place(tmp_path):
    (tmp_path / "git/.git").mkdir(parents=True)
    with pytest.raises(RuntimeError):
        updates.install(tmp_path / "git", archive(tmp_path / "1.zip", SHA_A, {"a": "1"}))
    with zipfile.ZipFile(tmp_path / "bad.zip", "w") as z:
        z.comment = SHA_A.encode()
        z.writestr("volleyball-stats-main/a", "1")
        z.writestr("volleyball-stats-main/../../evil", "1")
    with pytest.raises(RuntimeError):
        updates.install(tmp_path / "app", tmp_path / "bad.zip")
    assert not (tmp_path / "evil").exists()


def test_behind_and_newer_by_the_feed(monkeypatch, tmp_path):
    commits = ["c" * 40, SHA_B, SHA_A]
    monkeypatch.setattr(updates, "feed", lambda: commits)
    (tmp_path / updates.INSTALLED).write_text(json.dumps({"commit": SHA_A, "files": []}), encoding="utf-8")
    assert updates.behind(tmp_path)["behind"] == 2
    (tmp_path / updates.INSTALLED).write_text(json.dumps({"commit": "d" * 40, "files": []}), encoding="utf-8")
    assert updates.behind(tmp_path)["behind"] == 3
    (tmp_path / updates.INSTALLED).write_text(json.dumps({"commit": commits[0], "files": []}), encoding="utf-8")
    assert updates.behind(tmp_path) is None

    assert updates.newer(SHA_B, SHA_A) and not updates.newer(SHA_A, SHA_B)
    assert updates.newer(SHA_B, "d" * 40) and not updates.newer("d" * 40, SHA_A) and not updates.newer("d" * 40, "e" * 40)


def test_get_on_windows_has_powershell_bring_a_missing_root_certificate(monkeypatch):
    tries, ran = [], []

    def urlopen(request, timeout):
        tries.append(request.full_url)
        if len(tries) == 1:
            raise updates.urllib.error.URLError(updates.ssl.SSLCertVerificationError("unable to get local issuer certificate"))
        return "answer"

    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(updates.subprocess, "run", lambda command, **_: ran.append(command))
    monkeypatch.setattr(updates.sys, "platform", "win32")
    assert updates.get(updates.ARCHIVE) == "answer"
    assert tries == [updates.ARCHIVE] * 2 and updates.ARCHIVE in ran[0][-1]

    tries.clear()
    monkeypatch.setattr(updates.sys, "platform", "darwin")
    with pytest.raises(updates.urllib.error.URLError):
        updates.get(updates.ARCHIVE)
