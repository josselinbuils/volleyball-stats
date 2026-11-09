#!/bin/sh
# Installs volleyball-stats, then starts it; run again, it only starts it.
#
#   curl -LsSf https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.sh | sh
#
# macOS, Linux or Windows' Ubuntu (WSL2). It installs what is missing (Homebrew on a Mac, then git, ffmpeg and uv), the
# code in ~/volleyball-stats, a shortcut on the desktop (a Mac's, or Windows' for WSL2), and opens the app in the browser.
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

# The launcher, with the PATH this script found the tools on (a shortcut opens with the system's default one, which
# lacks Homebrew's /opt/homebrew/bin on Apple chips), then the shortcut on the desktop.
mkdir -p "$HOME/.local/bin"
launcher=$HOME/.local/bin/volleyball-stats
printf '#!/bin/sh\nexport PATH="%s:$PATH"\ncd "%s" && exec "%s" run volleyball-stats "$@"\n' "$PATH" "$DIR" "$UV" >"$launcher"
chmod +x "$launcher"
shortcut=""
if [ "$(uname -s)" = Darwin ] && [ -d "$HOME/Desktop" ]; then
  cp "$launcher" "$HOME/Desktop/Volleyball Stats.command"
  shortcut=yes
elif [ -n "$WSL_DISTRO_NAME" ] && command -v powershell.exe >/dev/null 2>&1; then
  # The desktop Windows shows, which OneDrive often moves out of the user's folder.
  windows=$(cd /mnt/c 2>/dev/null && powershell.exe -NoProfile -Command "[Environment]::GetFolderPath('Desktop')" 2>/dev/null </dev/null | tr -d '\r')
  desktop=$(wslpath "$windows" 2>/dev/null || true)
  if [ -n "$windows" ] && [ -n "$desktop" ] && [ -d "$desktop" ]; then
    printf '@echo off\r\nwsl.exe -d %s -- "%s"\r\n' "$WSL_DISTRO_NAME" "$launcher" >"$desktop/Volleyball Stats.bat"
    shortcut=yes
  fi
fi

if [ -n "$shortcut" ]; then
  next="open \"Volleyball Stats\" on the desktop"
else
  next="run this same line again"
fi
say "Starting volleyball-stats: the first start takes a few minutes. Next time, $next."
exec "$UV" run volleyball-stats
