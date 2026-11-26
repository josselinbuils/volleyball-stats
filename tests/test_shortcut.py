import os
import plistlib

import pytest

from volleyball_stats import shortcut

PAIR = ("#2c2b79", "#d01214")


class TestShortcut:
    def test_starts_the_launcher_with_no_window_on_windows(self):
        program, arguments = shortcut.windows_command("Ubuntu-24.04", "/home/a/.local/bin/volleyball-stats")
        assert program == "conhost.exe"
        assert arguments == '--headless wsl.exe -d Ubuntu-24.04 -- "/home/a/.local/bin/volleyball-stats"'
        # The app on Windows itself: its launcher, a .cmd.
        assert shortcut.windows_command(None, "C:\\Users\\a b\\.local\\bin\\volleyball-stats.cmd") == ("conhost.exe", '--headless cmd.exe /c "C:\\Users\\a b\\.local\\bin\\volleyball-stats.cmd"')

    def test_quotes_for_powershell(self):
        assert shortcut.ps_quote("C:\\Users\\O'Neil\\Desktop") == "'C:\\Users\\O''Neil\\Desktop'"

    def test_describes_a_mac_app_with_no_dock_icon(self):
        info = plistlib.loads(shortcut.info_plist())
        assert info["CFBundleExecutable"] == "volleyball-stats" and info["LSUIElement"] is True

    @pytest.mark.skipif(os.name == "nt", reason="a Mac's rights")
    def test_makes_a_mac_app_in_place_of_the_command(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shortcut.Path, "home", lambda: tmp_path)
        (tmp_path / "Desktop").mkdir()
        (tmp_path / "Desktop" / "Volleyball Stats.command").write_text("", encoding="utf-8")
        made = shortcut.make_mac(PAIR)
        assert [p.parent.name for p in made] == ["Applications", "Desktop"]
        assert not (tmp_path / "Desktop" / "Volleyball Stats.command").exists()
        program = made[0] / "Contents/MacOS/volleyball-stats"
        assert program.stat().st_mode & 0o111 and str(shortcut.LAUNCHER) in program.read_text(encoding="utf-8")
        assert (made[0] / "Contents/Resources/volleyball-stats.icns").stat().st_size > 0

    def test_is_made_again_on_a_new_version_or_colours(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shortcut, "MADE", tmp_path / "shortcut")
        assert not shortcut.made(PAIR)
        shortcut.MADE.write_text(shortcut.key(PAIR), encoding="utf-8")
        assert shortcut.made(PAIR) and not shortcut.made(("#2c2b79", "#ffcc00"))

    def test_names_the_icon_after_its_colours(self):
        assert shortcut.icon_name(PAIR, ".ico") == "volleyball-stats-2c2b79-d01214.ico"

    @pytest.mark.parametrize("system", ["wsl", "windows"])
    def test_makes_windows_shortcuts_with_the_icon_in_place_of_the_bat(self, tmp_path, monkeypatch, system):
        folders = {"C:\\Desktop": tmp_path / "desktop", "C:\\Programs": tmp_path / "programs", "C:\\Local": tmp_path / "local"}
        for folder in folders.values():
            folder.mkdir()
        (folders["C:\\Desktop"] / "Volleyball Stats.bat").write_text("", encoding="utf-8")
        scripts = []

        def powershell(script):
            scripts.append(script)
            return "C:\\Desktop\nC:\\Programs\nC:\\Local\nC:\\Windows"

        def wsl_path(windows):
            folder, _, name = windows.partition("\\Volleyball Stats")
            return folders[folder] / f"Volleyball Stats{name}"

        monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
        monkeypatch.setattr(shortcut.doctor, "system", lambda: system)
        monkeypatch.setattr(shortcut, "run_powershell", powershell)
        monkeypatch.setattr(shortcut, "local_path", lambda windows: folders.get(windows) or wsl_path(windows))
        shortcut.make_windows(PAIR)
        assert (folders["C:\\Local"] / "Volleyball Stats" / "volleyball-stats-2c2b79-d01214.ico").stat().st_size > 0
        assert not (folders["C:\\Desktop"] / "Volleyball Stats.bat").exists()
        assert "C:\\Local\\Volleyball Stats\\volleyball-stats-2c2b79-d01214.ico" in scripts[1] and "conhost.exe" in scripts[1]
        assert ("cmd.exe" if system == "windows" else "wsl.exe") in scripts[1]

    def test_moves_an_older_launcher_to_stats(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shortcut, "LAUNCHER", tmp_path / "volleyball-stats")
        shortcut.update_launcher()
        shortcut.LAUNCHER.write_text('#!/bin/sh\ncd "/x" && exec "/uv" run volleyball-stats "$@"\n', encoding="utf-8")
        shortcut.update_launcher()
        assert shortcut.LAUNCHER.read_text(encoding="utf-8") == '#!/bin/sh\ncd "/x" && exec "/uv" run stats "$@"\n'
