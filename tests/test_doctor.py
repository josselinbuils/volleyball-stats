from volleyball_stats import doctor


def test_fetch_models_tells_the_models_done_of_those_missing(monkeypatch, tmp_path, capsys):
    from volleyball_stats import ball, identity

    paths = [tmp_path / "a.pt", tmp_path / "b.pt"]
    monkeypatch.setattr(doctor, "model_files", lambda: paths)
    monkeypatch.setattr(ball, "WEIGHTS_PATH", paths[0])
    monkeypatch.setattr(identity, "REID", paths[1])
    monkeypatch.setattr(ball, "load_model", lambda device: paths[0].write_text("x"))
    monkeypatch.setattr(identity, "load_reid", lambda device: paths[1].write_text("x"))

    doctor.fetch_models()

    told = [float(line.split()[1]) for line in capsys.readouterr().out.splitlines() if line.startswith("::progress ")]
    assert told == [0.0, 0.5, 1.0]
