#!/bin/sh
# volleyball-stats.dmg: the app to drag to Applications. Its first open installs volleyball-stats (install.sh in a Terminal
# window, its steps and bars, nothing asked), then opens it again: the app. Its first start makes it the shortcut
# (shortcut.py: the club's icon). On a Mac (codesign, hdiutil):
#
#   sh packaging/macos/build.sh    # packaging/macos/dist/volleyball-stats.dmg
#
# Signed ad hoc (no Apple account): macOS asks once before its first open (System Settings → Privacy & Security → Open
# Anyway). It changes rarely: the code comes from GitHub at install, then updates itself.
set -e

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
app="$work/dmg/Volleyball Stats.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$here/volleyball-stats.icns" "$root/install.sh" "$app/Contents/Resources/"

cat >"$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Volleyball Stats</string>
  <key>CFBundleDisplayName</key><string>Volleyball Stats</string>
  <key>CFBundleIdentifier</key><string>io.github.josselinbuils.volleyball-stats</string>
  <key>CFBundleExecutable</key><string>volleyball-stats</string>
  <key>CFBundleIconFile</key><string>volleyball-stats</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

cat >"$app/Contents/MacOS/volleyball-stats" <<'PROGRAM'
#!/bin/sh
# Installed: the app, apart from this process (shortcut.MAC_PROGRAM). Else install.sh in a Terminal window, which opens
# this app again at the end.
launcher="$HOME/.local/bin/volleyball-stats"
if [ -x "$launcher" ]; then
  nohup "$launcher" >/dev/null 2>&1 </dev/null &
  exit 0
fi
app=$(cd "$(dirname "$0")/../.." && pwd)
script="${TMPDIR:-/tmp}/volleyball-stats-install.command"
printf '#!/bin/sh\nVOLLEYBALL_STATS_APP="%s" exec /bin/sh "%s"\n' "$app" "$app/Contents/Resources/install.sh" >"$script"
chmod +x "$script"
xattr -d com.apple.quarantine "$script" 2>/dev/null || true
exec open -a Terminal "$script"
PROGRAM
chmod +x "$app/Contents/MacOS/volleyball-stats"

codesign --force --deep --sign - "$app"
ln -s /Applications "$work/dmg/Applications"
mkdir -p "$here/dist"
hdiutil create -volname "Volleyball Stats" -srcfolder "$work/dmg" -ov -format UDZO "$here/dist/volleyball-stats.dmg"
