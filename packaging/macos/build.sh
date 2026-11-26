#!/bin/sh
# volleyball-stats.dmg: an app that installs volleyball-stats at its first open (install.sh in a Terminal window, its
# steps and bars, nothing asked), then opens it as the desktop's icon does. On a Mac (codesign, hdiutil):
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
  <key>CFBundleIdentifier</key><string>io.github.josselinbuils.volleyball-stats.installer</string>
  <key>CFBundleExecutable</key><string>volleyball-stats</string>
  <key>CFBundleIconFile</key><string>volleyball-stats</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
</dict>
</plist>
PLIST

cat >"$app/Contents/MacOS/volleyball-stats" <<'PROGRAM'
#!/bin/sh
# Installed: the app, as its desktop icon opens it. Else install.sh in a Terminal window, which opens it at the end.
launcher="$HOME/.local/bin/volleyball-stats"
[ -x "$launcher" ] && exec "$launcher"
script="${TMPDIR:-/tmp}/volleyball-stats-install.command"
printf '#!/bin/sh\nVOLLEYBALL_STATS_DETACH=1 exec /bin/sh "%s"\n' "$(cd "$(dirname "$0")/../Resources" && pwd)/install.sh" >"$script"
chmod +x "$script"
xattr -d com.apple.quarantine "$script" 2>/dev/null || true
exec open -a Terminal "$script"
PROGRAM
chmod +x "$app/Contents/MacOS/volleyball-stats"

codesign --force --deep --sign - "$app"
ln -s /Applications "$work/dmg/Applications"
mkdir -p "$here/dist"
hdiutil create -volname "Volleyball Stats" -srcfolder "$work/dmg" -ov -format UDZO "$here/dist/volleyball-stats.dmg"
