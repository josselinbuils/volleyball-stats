import hashlib
import io
import os
import zipfile

import pytest

from volleyball_stats import tools, updates


def zipped(name: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(f"build/bin/{name}", "program")
    return out.getvalue()


def test_fetch_checks_each_file_then_puts_the_programs_on_the_path(monkeypatch, tmp_path):
    suffix = ".exe" if os.name == "nt" else ""
    content = {f"https://x/{p}.zip": zipped(p + suffix) for p in tools.PROGRAMS}
    way = [(url, hashlib.sha256(data).hexdigest()) for url, data in content.items()]
    monkeypatch.setattr(tools, "DIR", tmp_path / "ffmpeg")
    monkeypatch.setattr(tools, "BIN", tmp_path / "ffmpeg/bin")
    monkeypatch.setattr(tools, "build", lambda: [[(way[0][0], "0" * 64)], way])

    def download(url, to, told=None):
        to.write_bytes(content[url])
        told(len(content[url]), len(content[url]))

    monkeypatch.setattr(updates, "download", download)
    monkeypatch.setenv("PATH", "elsewhere")
    told = []
    tools.fetch(told.append)

    # The first way's file is not the expected one: the second's are taken.
    assert {p.name for p in (tmp_path / "ffmpeg/bin").iterdir()} == {p + suffix for p in tools.PROGRAMS}
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tmp_path / "ffmpeg/bin")
    assert told[-2:] == [0.5, 1.0]


def test_fetch_says_when_no_build_fits(monkeypatch):
    monkeypatch.setattr(tools, "build", lambda: None)
    with pytest.raises(RuntimeError):
        tools.fetch()


@pytest.mark.parametrize(
    "line, expected",
    [("9.1-full_build-www.gyan.dev", "9.1"), ("6.1.1-3ubuntu5", "6.1.1"), ("n9.0", "9.0"), ("N-121000-g1234", "N-121000-g1234")],
)
def test_version_keeps_the_number_of_a_build_s_label(monkeypatch, line, expected):
    monkeypatch.setattr(tools.shutil, "which", lambda name: "ffmpeg")
    monkeypatch.setattr(tools.subprocess, "run", lambda *a, **k: type("Run", (), {"stdout": f"ffmpeg version {line} Copyright"})())
    assert tools.version() == expected
