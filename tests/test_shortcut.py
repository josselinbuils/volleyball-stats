import plistlib

from volleyball_stats import shortcut


class TestShortcut:
    def test_starts_the_launcher_with_no_window_on_windows(self):
        program, arguments = shortcut.windows_command("Ubuntu-24.04", shortcut.Path("/home/a/.local/bin/volleyball-stats"))
        assert program == "conhost.exe"
        assert arguments == '--headless wsl.exe -d Ubuntu-24.04 -- "/home/a/.local/bin/volleyball-stats"'

    def test_quotes_for_powershell(self):
        assert shortcut.ps_quote("C:\\Users\\O'Neil\\Desktop") == "'C:\\Users\\O''Neil\\Desktop'"

    def test_describes_a_mac_app_with_no_dock_icon(self):
        info = plistlib.loads(shortcut.info_plist())
        assert info["CFBundleExecutable"] == "volleyball-stats" and info["LSUIElement"] is True
        assert (shortcut.ICON.parent / f"{info['CFBundleIconFile']}.icns").exists()

    def test_makes_a_mac_app_in_place_of_the_command(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shortcut.Path, "home", lambda: tmp_path)
        (tmp_path / "Desktop").mkdir()
        (tmp_path / "Desktop" / "Volleyball Stats.command").write_text("")
        made = shortcut.make_mac()
        assert [p.parent.name for p in made] == ["Applications", "Desktop"]
        assert not (tmp_path / "Desktop" / "Volleyball Stats.command").exists()
        program = made[0] / "Contents/MacOS/volleyball-stats"
        assert program.stat().st_mode & 0o111 and str(shortcut.LAUNCHER) in program.read_text()

    def test_is_made_again_once_per_version(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shortcut, "MADE", tmp_path / "shortcut")
        assert not shortcut.made()
        shortcut.MADE.write_text(str(shortcut.VERSION))
        assert shortcut.made()
