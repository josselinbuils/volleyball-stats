#!/bin/sh
# volleyball-stats.dmg: the app to drag to Applications (app.swift, built by app.sh). Its first open installs
# volleyball-stats (install.sh in a Terminal window, its steps and bars, nothing asked), then opens it again: the app.
# Its first start makes it the shortcut (shortcut.py: the club's icon). On a Mac (codesign, hdiutil):
#
#   VERSION=1.2 sh packaging/macos/build.sh    # packaging/macos/dist/volleyball-stats.dmg
#
# Its version is the release's tag, which the Installers workflow passes; "dev" without one.
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
cp "$here/Info.plist" "$app/Contents/"
for key in CFBundleShortVersionString CFBundleVersion; do
  plutil -replace "$key" -string "${VERSION:-dev}" "$app/Contents/Info.plist"
done
cp "$here/volleyball-stats" "$app/Contents/MacOS/"
cp "$here/volleyball-stats.icns" "$root/install.sh" "$app/Contents/Resources/"

codesign --force --deep --sign - "$app"
ln -s /Applications "$work/dmg/Applications"
mkdir -p "$here/dist"
hdiutil create -volname "Volleyball Stats" -srcfolder "$work/dmg" -ov -format UDZO "$here/dist/volleyball-stats.dmg"
