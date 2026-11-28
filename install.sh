#!/bin/sh
# Installs volleyball-stats, then starts it; run again, it only starts it.
#
#   curl -LsSf https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.sh | sh
#
# macOS, Linux or Windows' Ubuntu (WSL2): uv (its own installer), the code from GitHub's archive (no git: updates.py,
# the app then updating it by itself), the libraries, ffmpeg and the models (Diagnostics' download); on Linux and WSL2
# ffmpeg and curl through apt. Run from a developer's git checkout (`./install.sh` in it), it keeps that checkout. The
# .dmg's app runs it so (packaging/macos). Then the launcher, and the app, which makes its shortcut (shortcut.py).
set -e

RAW=https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main
case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in fr*) FR=1 ;; *) FR= ;; esac
[ "$(uname -s)" = Darwin ] && defaults read -g AppleLanguages 2>/dev/null | sed -n 2p | grep -q '"fr' && FR=1
# say FRENCH ENGLISH, or say ENGLISH
say() { if [ -n "$FR" ] || [ -z "$2" ]; then printf '\n\033[1m%s\033[0m\n' "$1"; else printf '\n\033[1m%s\033[0m\n' "$2"; fi; }
# set -e stops with the failed command's own words only.
failed() {
  status=$?
  [ "$status" -eq 0 ] || say "L'installation a échoué : relancez-la une fois réglé ce qui est dit au-dessus." \
    "The installation failed: run it again once what is said above is fixed."
}
trap failed EXIT

# Run from a copy of the code, that copy; else ~/volleyball-stats.
here=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)
if [ -n "$here" ] && [ -f "$here/pyproject.toml" ] && grep -q 'name = "volleyball-stats"' "$here/pyproject.toml"; then
  DIR=$here
else
  DIR=${VOLLEYBALL_STATS_DIR:-$HOME/volleyball-stats}
fi
export PATH="$HOME/.local/bin:$PATH"

# Linux and WSL2: ffmpeg (the app brings its own on a Mac and Windows) and curl through apt.
if [ "$(uname -s)" != Darwin ]; then
  missing=""
  for tool in ffmpeg curl; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
  done
  if [ -n "$missing" ]; then
    say "Installation de$missing : votre mot de passe est demandé (rien ne s'affiche en le tapant)." \
      "Installing$missing: it asks for your password (typing shows nothing)."
    sudo apt-get update </dev/tty
    # shellcheck disable=SC2086
    sudo apt-get install -y $missing </dev/tty
  fi
fi
if ! command -v uv >/dev/null 2>&1; then
  say "Installation de uv…" "Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
# A developer's git checkout stays one (its owner pulls); else GitHub's archive, which the app updates by itself.
if [ ! -d "$DIR/.git" ] && [ ! -f "$DIR/.install.json" ]; then
  say "Téléchargement de volleyball-stats…" "Downloading volleyball-stats…"
  work=$(mktemp -d)
  curl -fsSL "$RAW/src/volleyball_stats/updates.py" -o "$work/updates.py"
  (cd "$work" && uv run --no-project --with certifi --python 3.12 -- python -I "$work/updates.py" install "$DIR")
  rm -rf "$work"
fi
cd "$DIR"
say "Installation des bibliothèques : la première fois, de longues minutes…" "Installing the libraries: the first time, many minutes…"
uv sync
say "Téléchargement de ffmpeg et des modèles…" "Downloading ffmpeg and the models…"
uv run python -m volleyball_stats.doctor --models
UV=$(command -v uv)

# The launcher, with the PATH this script found the tools on (a shortcut opens with the system's default one, which
# lacks ~/.local/bin, and Homebrew's /opt/homebrew/bin on Apple chips). The app makes its shortcut on it at start (shortcut.py).
mkdir -p "$HOME/.local/bin"
launcher=$HOME/.local/bin/volleyball-stats
printf '#!/bin/sh\nexport PATH="%s:$PATH"\ncd "%s" && exec "%s" run stats "$@"\n' "$PATH" "$DIR" "$UV" >"$launcher"
chmod +x "$launcher"
if [ -n "$VOLLEYBALL_STATS_APP" ]; then
  # The .dmg's app, opened again: the app, apart from this window.
  say "Ouverture de Volleyball Stats : vous pouvez fermer cette fenêtre." "Opening Volleyball Stats: you can close this window."
  open "$VOLLEYBALL_STATS_APP"
  exit 0
fi
if [ "$(uname -s)" = Darwin ]; then
  next="open \"Volleyball Stats\" in Applications"
elif [ -n "$WSL_DISTRO_NAME" ]; then
  next="open \"Volleyball Stats\" on the desktop"
else
  next="open \"Volleyball Stats\" in the applications menu"
fi
say "Starting volleyball-stats: the first start takes a few minutes. Next time, $next."
exec "$UV" run stats
