#!/bin/sh
# Installs volleyball-stats, then starts it; run again, it only starts it.
#
#   curl -LsSf https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.sh | sh
#
# macOS, Linux or Windows' Ubuntu (WSL2). It installs what is missing (Homebrew on a Mac, then git, ffmpeg and uv), the
# code in ~/volleyball-stats, a shortcut on the desktop, and opens the app in the browser.
set -e

REPO=https://github.com/josselinbuils/volleyball-stats.git
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# Run from a copy of the code, that copy; else ~/volleyball-stats.
here=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)
if [ -n "$here" ] && [ -f "$here/pyproject.toml" ] && grep -q 'name = "volleyball-stats"' "$here/pyproject.toml"; then
  DIR=$here
else
  DIR=${VOLLEYBALL_STATS_DIR:-$HOME/volleyball-stats}
fi

if [ "$(uname -s)" = Darwin ]; then
  for brew in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if ! command -v brew >/dev/null 2>&1 && [ -x "$brew" ]; then
      eval "$("$brew" shellenv)"
    fi
  done
  if ! command -v brew >/dev/null 2>&1; then
    say "Installing Homebrew: it asks for this Mac's password (typing shows nothing)."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty
    for brew in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      [ -x "$brew" ] && eval "$("$brew" shellenv)"
    done
  fi
  missing=""
  for tool in git ffmpeg uv; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
  done
  if [ -n "$missing" ]; then
    say "Installing$missing…"
    # shellcheck disable=SC2086
    brew install $missing
  fi
else
  missing=""
  for tool in git ffmpeg curl; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
  done
  if [ -n "$missing" ]; then
    say "Installing$missing: it asks for your password (typing shows nothing)."
    sudo apt-get update </dev/tty
    # shellcheck disable=SC2086
    sudo apt-get install -y $missing </dev/tty
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
fi

if [ ! -d "$DIR/.git" ]; then
  say "Downloading volleyball-stats into $DIR…"
  git clone "$REPO" "$DIR"
fi
cd "$DIR"
UV=$(command -v uv)

# The shortcut: on the desktop (a Mac's, or Windows' for WSL2), and the command `volleyball-stats` in a terminal.
mkdir -p "$HOME/.local/bin"
printf '#!/bin/sh\ncd "%s" && exec "%s" run volleyball-stats "$@"\n' "$DIR" "$UV" >"$HOME/.local/bin/volleyball-stats"
chmod +x "$HOME/.local/bin/volleyball-stats"
if [ "$(uname -s)" = Darwin ] && [ -d "$HOME/Desktop" ]; then
  cp "$HOME/.local/bin/volleyball-stats" "$HOME/Desktop/Volleyball Stats.command"
elif [ -n "$WSL_DISTRO_NAME" ] && command -v cmd.exe >/dev/null 2>&1; then
  profile=$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')
  desktop=$(wslpath "$profile" 2>/dev/null)/Desktop
  if [ -n "$profile" ] && [ -d "$desktop" ]; then
    printf '@echo off\r\nwsl.exe -d %s -- "%s"\r\n' "$WSL_DISTRO_NAME" "$HOME/.local/bin/volleyball-stats" >"$desktop/Volleyball Stats.bat"
  fi
fi

say "Starting volleyball-stats: the first start takes a few minutes. Next time, open \"Volleyball Stats\" on the desktop."
exec "$UV" run volleyball-stats
