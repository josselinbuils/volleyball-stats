import os
import shlex
import shutil
import subprocess
import sys

import pytest

from volleyball_stats import transfer

# The server reached by ssh, here: its python3 is this one.
FAKE_SSH = "import shlex, subprocess, sys\nsys.exit(subprocess.call([sys.executable if w == 'python3' else w for w in shlex.split(sys.argv[2])]))\n"
SOURCE = {"m/a.json": "aa", "m/review/x.js": "x", "m/b/c.txt": "c", "m/v.mp4": "vid", "m/video/films/f.mp4": "film", "m/.t.tmp": "tmp", "f.json": "file", "m/backup-sync-1/z": "z"}
DEST = {"m/a.json": "old", "m/gone.txt": "g", "m/olddir/k": "k", "m/review/keep.js": "k", "m/b/c.txt": "c"}
# The app's commands (`backup`, `sync`, `matches`); SSH and BASE filled in.
CASES = [
    ["-rt", "--delete", "--exclude=review", "--exclude=.*.tmp", "--exclude=backup-*", "BASE/src/m", "BASE/dst/"],
    ["-rt", "--delete", "--exclude=review", "BASE/src/m/", "BASE/dst/m"],
    ["-rt", "--delete", "--delay-updates", "--exclude=review", "-e", "SSH", "BASE/src/m", "here:BASE/dst/"],
    ["-rt", "--delete", "--exclude=review", "-e", "SSH", "here:BASE/src/m/", "BASE/dst/m"],
    ["-rt", "--delete", "--include=*/video/films/*.mp4", "--exclude=*.mp4", "-e", "SSH", "here:BASE/src/", "BASE/dst/"],
    ["-rt", "--delete", "--include=/m/**.mp4", "--exclude=*.mp4", "-e", "SSH", "BASE/src/", "here:BASE/dst/"],
    ["-rt", "--update", "-e", "SSH", "BASE/src/m", "BASE/src/f.json", "here:BASE/dst/"],
    ["-rt", "--update", "-e", "SSH", "here:BASE/src/f.json", "BASE/dst/f2.json"],
    ["-rcn", "--delete", "--exclude=review", "-e", "SSH", "BASE/src/m/", "here:BASE/dst/m/"],
    ["-r", "--delete", "--backup", "--backup-dir=bk", "-e", "SSH", "here:BASE/src/m/", "BASE/dst/m"],
    ["-rt", "--delete", "--backup", "--backup-dir=BASE/aside/m", "-e", "SSH", "here:BASE/src/m/", "BASE/dst/m"],
    ["-rt", "-e", "SSH", "here:BASE/src/missing/", "BASE/dst/m"],
]


def make(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        os.utime(path, (1000 + len(rel), 1000 + len(rel)))


def tree(root, times=True):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else (p.read_text(encoding="utf-8"), int(p.stat().st_mtime) if times else None) for p in sorted(root.rglob("*"))}


@pytest.fixture
def base(tmp_path):
    make(tmp_path / "src", SOURCE)
    make(tmp_path / "dst", DEST)
    (tmp_path / "ssh.py").write_text(FAKE_SSH, encoding="utf-8")
    return tmp_path


def run(tool, args, base, dry=False):
    ssh = shlex.join([sys.executable, str(base / "ssh.py")]) if tool != "rsync" else str(base / "ssh.sh")
    args = [ssh if a == "SSH" else a.replace("BASE", base.as_posix()) for a in args]
    command = [tool] if tool == "rsync" else [sys.executable, transfer.__file__]
    done = subprocess.run([*command, *(["--dry-run"] if dry else []), "--itemize-changes", *args], capture_output=True, text=True, encoding="utf-8")
    lines = sorted(line.replace(base.as_posix(), "BASE") for line in done.stdout.splitlines() if line.strip() and not line.startswith(".d"))
    return done.returncode, lines, done.stderr


@pytest.mark.skipif(not (shutil.which("rsync") and shutil.which("sh")), reason="no rsync to compare with")
@pytest.mark.parametrize("dry", [True, False])
@pytest.mark.parametrize("args", CASES, ids=lambda a: " ".join(a))
def test_does_what_rsync_does(tmp_path, args, dry):
    got = {}
    for tool in ("rsync", "stand-in"):
        here = tmp_path / tool
        make(here / "src", SOURCE)
        make(here / "dst", DEST)
        (here / "ssh.py").write_text(FAKE_SSH, encoding="utf-8")
        (here / "ssh.sh").write_text('#!/bin/sh\nshift\nexec sh -c "$*"\n', encoding="utf-8")
        (here / "ssh.sh").chmod(0o755)
        code, lines, _ = run(tool, args, here, dry)
        shutil.rmtree(here / "src")
        (here / "ssh.py").unlink()
        (here / "ssh.sh").unlink()
        got[tool] = code, lines, tree(here, times="-rt" in args)
    assert got["stand-in"] == got["rsync"]


class TestStandIn:
    def test_sends_a_folder_its_filters_deletions_and_times(self, base):
        code, lines, _ = run("stand-in", CASES[2], base)
        assert code == 0 and "<f+++++++++ m/v.mp4" in lines and "<f.s....... m/a.json" in lines and "*deleting   m/olddir/k" in lines
        assert tree(base / "dst") == {
            "m": None, "m/.t.tmp": ("tmp", 1008), "m/a.json": ("aa", 1008), "m/b": None, "m/b/c.txt": ("c", 1009), "m/backup-sync-1": None,
            "m/backup-sync-1/z": ("z", 1017), "m/review": None, "m/review/keep.js": ("k", 1016), "m/v.mp4": ("vid", 1007), "m/video": None,
            "m/video/films": None, "m/video/films/f.mp4": ("film", 1019),
        }  # fmt: skip

    def test_a_dry_run_changes_nothing(self, base):
        before = tree(base)
        code, lines, _ = run("stand-in", CASES[2], base, dry=True)
        assert code == 0 and lines and tree(base) == before

    def test_brings_one_file_to_its_path(self, base):
        code, lines, _ = run("stand-in", CASES[7], base)
        assert (code, lines) == (0, [">f+++++++++ f.json"]) and (base / "dst" / "f2.json").read_text(encoding="utf-8") == "file"

    def test_keeps_a_newer_file_with_update(self, base):
        make(base / "dst", {"f.json": "newer"})
        os.utime(base / "dst" / "f.json", (5000, 5000))
        run("stand-in", CASES[6], base)
        assert (base / "dst" / "f.json").read_text(encoding="utf-8") == "newer" and (base / "dst" / "m" / "a.json").read_text(encoding="utf-8") == "aa"

    def test_checksums_find_a_change_size_and_time_hide(self, base):
        make(base / "dst", {"m/b/c.txt": "C"})
        os.utime(base / "dst" / "m" / "b" / "c.txt", (1009, 1009))
        _, lines, _ = run("stand-in", CASES[8], base)
        assert "<fc.T...... b/c.txt" in lines

    def test_sets_aside_what_it_replaces_or_deletes(self, base):
        code, _, _ = run("stand-in", CASES[9], base)
        assert code == 0 and tree(base / "dst" / "m" / "bk", times=False) == {"a.json": ("old", None), "gone.txt": ("g", None), "olddir": None, "olddir/k": ("k", None), "review": None, "review/keep.js": ("k", None)}

    def test_a_copy_sharing_a_file_by_a_hard_link_keeps_its_own(self, base):
        # The server's hourly copies share unchanged files (`backup.snapshot`).
        older = base / "older.json"
        os.link(base / "dst" / "m" / "a.json", older)
        run("stand-in", CASES[2], base)
        assert older.read_text(encoding="utf-8") == "old" and (base / "dst" / "m" / "a.json").read_text(encoding="utf-8") == "aa"

    def test_says_a_source_is_missing_as_rsync(self, base):
        code, lines, stderr = run("stand-in", CASES[11], base)
        assert code == transfer.PARTIAL and not lines and "No such file or directory" in stderr

    def test_a_file_gone_while_it_goes_is_told_as_vanished(self, tmp_path):
        vanished = []
        assert list(transfer.opened([("a", str(tmp_path / "a"))], vanished)) == [] and vanished == ["a"]

    def test_reads_rsync_s_filter_rules(self):
        rules = transfer.Rules([("+", "*/video/films/*.mp4"), ("+", "/m/**.mp4"), ("-", "*.mp4"), ("-", "review"), ("-", "tmp/")])
        assert not rules.out("x/video/films/a.mp4", False) and not rules.out("m/video/b.mp4", False)
        assert rules.out("n/video/b.mp4", False) and rules.out("a/review", True) and rules.out("review", False)
        assert rules.out("a/tmp", True) and not rules.out("a/tmp", False)

    def test_tells_a_drive_from_a_host(self):
        assert transfer.place("root@h:/site/") == ("root@h", "/site/") and transfer.place("C:\\x") == (None, "C:\\x") and transfer.place("/a:b") == (None, "/a:b")

    def test_runs_rsync_when_installed(self, monkeypatch):
        monkeypatch.setattr(transfer.shutil, "which", lambda name: None)
        assert transfer.local(["rsync", "-r", "a", "b"]) == [sys.executable, transfer.os.path.abspath(transfer.__file__), "-r", "a", "b"]
        monkeypatch.setattr(transfer.shutil, "which", lambda name: "/usr/bin/rsync")
        assert transfer.local(["rsync", "-r", "a", "b"]) == ["rsync", "-r", "a", "b"]
