from volleyball_stats import doctor


def test_fetch_models_tells_the_models_done_of_those_missing(monkeypatch, tmp_path, capsys):
    from volleyball_stats import ball, identity, tools

    monkeypatch.setattr(tools, "fetchable", lambda: False)

    paths = [tmp_path / "a.pt", tmp_path / "b.pt"]
    monkeypatch.setattr(doctor, "model_files", lambda: paths)
    monkeypatch.setattr(ball, "WEIGHTS_PATH", paths[0])
    monkeypatch.setattr(identity, "REID", paths[1])
    monkeypatch.setattr(ball, "load_model", lambda device: paths[0].write_text("x", encoding="utf-8"))
    monkeypatch.setattr(identity, "load_reid", lambda device: paths[1].write_text("x", encoding="utf-8"))

    doctor.fetch_models()

    told = [float(line.split()[1]) for line in capsys.readouterr().out.splitlines() if line.startswith("::progress ")]
    assert told == [0.0, 0.5, 1.0]


def test_fetch_models_fetches_ffmpeg_first_by_its_bytes(monkeypatch, tmp_path, capsys):
    from volleyball_stats import ball, tools

    paths = [tmp_path / "a.pt"]
    monkeypatch.setattr(doctor, "model_files", lambda: paths)
    monkeypatch.setattr(ball, "WEIGHTS_PATH", paths[0])
    monkeypatch.setattr(ball, "load_model", lambda device: paths[0].write_text("x", encoding="utf-8"))
    monkeypatch.setattr(tools, "fetchable", lambda: True)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(tools, "fetch", lambda told: [told(0.5), told(1.0)])

    doctor.fetch_models()

    told = [float(line.split()[1]) for line in capsys.readouterr().out.splitlines() if line.startswith("::progress ")]
    assert told == [0.25, 0.5, 0.5, 1.0]


def test_tools_offers_the_download_where_the_app_installs_ffmpeg(monkeypatch, tmp_path):
    from volleyball_stats import git_check, tools

    monkeypatch.setattr(git_check, "ROOT", tmp_path)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(tools, "fetchable", lambda: True)
    found = doctor.tools()
    # No .git: git is not needed.
    assert (found["missing"], found["fetch"], found["command"]) == (["ffmpeg", "ffprobe"], True, None)

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(tools, "fetchable", lambda: False)
    found = doctor.tools()
    assert found["missing"] == ["ffmpeg", "ffprobe", "git"] and not found["fetch"] and found["command"]
