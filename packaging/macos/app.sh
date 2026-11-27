#!/bin/sh
# The Mac app's program (app.swift), for Apple chips and Intel, signed ad hoc. Built on a Mac with Xcode's command-line
# tools, then committed: the .dmg (build.sh) and the shortcut (shortcut.py) take it, no Mac needing Swift.
#
#   sh packaging/macos/app.sh    # packaging/macos/volleyball-stats, and the source's hash it was built from
set -e

here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
for arch in arm64 x86_64; do
  # No runtime compatibility libraries: the Command Line Tools ship them for Apple chips only, and nothing here needs them.
  swiftc -O -swift-version 5 -target "$arch-apple-macos11.3" -Xfrontend -disable-autolinking-runtime-compatibility \
    -Xfrontend -disable-autolinking-runtime-compatibility-concurrency -o "$work/$arch" "$here/app.swift"
done
lipo -create -output "$work/volleyball-stats" "$work/arm64" "$work/x86_64"
# Signed where it was built: codesign refused the file in the repository's folder (its extended attributes).
codesign --force --sign - --identifier io.github.josselinbuils.volleyball-stats "$work/volleyball-stats"
cp "$work/volleyball-stats" "$here/volleyball-stats"
shasum -a 256 "$here/app.swift" | cut -d ' ' -f 1 >"$here/volleyball-stats.source"
