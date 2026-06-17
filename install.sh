#!/usr/bin/env bash
# install.sh — checkup one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/vgrigolaia/checkup/main/install.sh | bash

set -e

REPO="vgrigolaia/checkup"
RAW_URL="https://raw.githubusercontent.com/${REPO}/main/checkup.py"
CMD_NAME="checkup"
SYSTEM_DIR="/usr/local/bin"
USER_DIR="$HOME/.local/bin"

# ── helpers ──────────────────────────────────────────────────────────────────

info()  { printf "\033[1;32m[checkup]\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m[checkup]\033[0m %s\n" "$*"; }
error() { printf "\033[1;31m[checkup]\033[0m %s\n" "$*" >&2; exit 1; }

# ── checks ───────────────────────────────────────────────────────────────────

command -v python3 &>/dev/null || error "python3 not found. Install Python 3.6+ and try again."

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,6) else 1)' \
  || error "Python 3.6 or higher is required (found $(python3 --version))."

if command -v curl &>/dev/null; then
  FETCH="curl -fsSL"
elif command -v wget &>/dev/null; then
  FETCH="wget -qO-"
else
  error "curl or wget is required to download checkup."
fi

# ── download ─────────────────────────────────────────────────────────────────

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

info "Downloading checkup from GitHub..."
$FETCH "$RAW_URL" > "$TMP"
chmod +x "$TMP"

# ── install ──────────────────────────────────────────────────────────────────

if [ -w "$SYSTEM_DIR" ]; then
  mv "$TMP" "$SYSTEM_DIR/$CMD_NAME"
  INSTALL_PATH="$SYSTEM_DIR/$CMD_NAME"
elif command -v sudo &>/dev/null; then
  info "Installing to $SYSTEM_DIR (requires sudo)..."
  sudo mv "$TMP" "$SYSTEM_DIR/$CMD_NAME"
  sudo chmod +x "$SYSTEM_DIR/$CMD_NAME"
  INSTALL_PATH="$SYSTEM_DIR/$CMD_NAME"
else
  warn "No sudo available — installing to $USER_DIR instead."
  mkdir -p "$USER_DIR"
  mv "$TMP" "$USER_DIR/$CMD_NAME"
  INSTALL_PATH="$USER_DIR/$CMD_NAME"
  # Warn if ~/.local/bin is not in PATH
  case ":$PATH:" in
    *":$USER_DIR:"*) ;;
    *) warn "Add $USER_DIR to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
  esac
fi

# ── done ─────────────────────────────────────────────────────────────────────

VERSION=$("$INSTALL_PATH" --version 2>/dev/null || echo "unknown")
info "Installed: $INSTALL_PATH  ($VERSION)"
info "Run: checkup --help"
