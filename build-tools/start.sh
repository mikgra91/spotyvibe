#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"/..

# ── macOS PATH injection ──────────────────────────────────────────────
# When Finder double-clicks a .command file, ~/.zshrc is NOT sourced.
# Homebrew's /opt/homebrew/bin is missing → only Apple's Python 3.9 is found.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# ── Colored output helpers ────────────────────────────────────────────
if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi

info()    { echo -e "${CYAN}ℹ ${RESET}$*"; }
warn()    { echo -e "${YELLOW}⚠ ${RESET}$*"; }
error()   { echo -e "${RED}✖ ${RESET}$*" >&2; }
success() { echo -e "${GREEN}✔ ${RESET}$*"; }

# ── Hash helper (cross-platform) ─────────────────────────────────────
_hash_file() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        echo "nohash"
    fi
}

# ── Python 3.10+ detection ───────────────────────────────────────────
PYTHON=""
for cmd in python3 python /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    error "Python 3.10+ is required but not found."
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "  Install via Homebrew:  brew install python@3.12"
        echo "  Or download from:      https://www.python.org/downloads/"
    else
        echo "  Debian/Ubuntu:  sudo apt install python3 python3-venv"
        echo "  Fedora:         sudo dnf install python3"
        echo "  Arch:           sudo pacman -S python"
    fi
    exit 1
fi

info "Using Python: $($PYTHON --version) at $(command -v "$PYTHON")"

# ── python3-venv probe (Debian/Ubuntu/Alpine) ────────────────────────
if ! "$PYTHON" -c "import ensurepip" 2>/dev/null; then
    error "Python venv module is not installed."
    if [[ -f /etc/debian_version ]]; then
        echo "  Run: sudo apt install python3-venv"
    elif [[ -f /etc/fedora-release ]]; then
        echo "  Run: sudo dnf install python3"
    elif [[ -f /etc/arch-release ]]; then
        echo "  Run: sudo pacman -S python"
    else
        echo "  Install your distribution's python3-venv equivalent."
    fi
    exit 1
fi

# ── Virtual environment management ────────────────────────────────────
if [[ ! -f .venv/bin/python ]]; then
    info "First run — setting up virtual environment..."
    "$PYTHON" -m venv .venv
    .venv/bin/pip install --upgrade pip --quiet
    if ! .venv/bin/pip install -r requirements-core.txt; then
        error "Dependency installation failed. Cleaning up..."
        rm -rf .venv
        exit 1
    fi
    _hash_file requirements-core.txt > .venv/.requirements_hash
    success "Setup complete!"
else
    # Check if dependencies changed since last install
    CURRENT_HASH=$(_hash_file requirements-core.txt)
    SAVED_HASH=""
    if [[ -f .venv/.requirements_hash ]]; then
        SAVED_HASH=$(cat .venv/.requirements_hash)
    fi
    if [[ "$CURRENT_HASH" != "$SAVED_HASH" && "$CURRENT_HASH" != "nohash" ]]; then
        info "Dependencies changed — updating virtual environment..."
        .venv/bin/pip install -r requirements-core.txt --quiet
        _hash_file requirements-core.txt > .venv/.requirements_hash
        success "Dependencies updated."
    fi
fi

# ── Port 5000 conflict detection ─────────────────────────────────────
PORT=5000

_port_busy() {
    if command -v lsof &>/dev/null; then
        lsof -i :"$PORT" -sTCP:LISTEN -t &>/dev/null
    elif command -v ss &>/dev/null; then
        ss -tlnp | grep -q ":${PORT} "
    else
        return 1   # can't check, assume free
    fi
}

if _port_busy; then
    error "Port $PORT is already in use."
    echo "  Port 5000 is required — Spotify OAuth redirect is fixed to http://127.0.0.1:5000/callback."
    if [[ "$(uname)" == "Darwin" ]]; then
        echo ""
        echo "  macOS AirPlay Receiver uses port 5000 by default."
        echo "  Disable it: System Settings → General → AirDrop & Handoff → AirPlay Receiver → Off"
        echo ""
    else
        PID=""
        if command -v lsof &>/dev/null; then
            PID=$(lsof -i :"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
        fi
        if [[ -n "$PID" ]]; then
            echo "  Process using port $PORT: PID $PID"
            echo "  Stop it with: kill $PID"
        else
            echo "  Find the process with: ss -tlnp | grep :$PORT"
        fi
    fi
    exit 1
fi

# ── Start Flask server ────────────────────────────────────────────────
info "Starting SpotyVibe at http://127.0.0.1:$PORT"
.venv/bin/python app.py &
SERVER_PID=$!

# Register trap immediately — before health check or browser open can fail under set -e
cleanup() {
    echo ""
    info "Shutting down SpotyVibe..."
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
    success "Stopped. Goodbye!"
    exit 0
}
trap cleanup SIGINT SIGTERM SIGHUP

# ── Wait for server readiness ─────────────────────────────────────────
READY=false
for i in $(seq 1 30); do
    if curl -sf -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then
        READY=true; break
    fi
    if ! command -v curl &>/dev/null; then
        if .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/')" 2>/dev/null; then
            READY=true; break
        fi
    fi
    sleep 0.5
done

if [[ "$READY" != "true" ]]; then
    error "Server did not start within 15 seconds."
    kill "$SERVER_PID" 2>/dev/null
    exit 1
fi

success "SpotyVibe is running!"

# ── Open default browser ─────────────────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    open "http://127.0.0.1:$PORT" || warn "Could not open browser. Open http://127.0.0.1:$PORT manually."
elif [[ -n "${DISPLAY:-}" ]] || [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    xdg-open "http://127.0.0.1:$PORT" 2>/dev/null \
        || sensible-browser "http://127.0.0.1:$PORT" 2>/dev/null \
        || true
else
    echo ""
    info "No display detected (headless/SSH). Open in your browser:"
    echo "  http://127.0.0.1:$PORT"
fi

# ── Block until server exits ─────────────────────────────────────────
success "Press Ctrl+C to stop."
wait "$SERVER_PID"

