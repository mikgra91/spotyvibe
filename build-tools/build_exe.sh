#!/bin/bash
# Build the SpotyVibe Windows executable (PyInstaller)
#
# Usage:
#   ./build-tools/build_exe.sh --package   # one-folder build (spotyvibe.spec)
#   ./build-tools/build_exe.sh --full      # one-file build (spotyvibe_onefile.spec)

set -e

usage() {
  echo "Usage: $0 [--package|--full]" >&2
}

MODE=""
for arg in "$@"; do
  case "$arg" in
    --package)
      MODE="package"
      ;;
    --full)
      MODE="full"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "$MODE" ]; then
  usage
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Ensure all build-time dependencies (including pywebview) are installed
python -m pip install -r requirements.txt --quiet

if [ "$MODE" = "package" ]; then
  SPEC="spotyvibe.spec"
  EXPECTED_OUT="dist/spotyvibe/spotyvibe.exe"
else
  SPEC="spotyvibe_onefile.spec"
  EXPECTED_OUT="dist/spotyvibe_onefile.exe"
fi

echo "=== SpotyVibe Desktop Build ==="
echo "Mode: $MODE"
echo "Spec: $SPEC"

pyinstaller --noconfirm --clean "$SPEC"

if [ -f "$EXPECTED_OUT" ]; then
  echo "Build OK: $EXPECTED_OUT"
else
  echo "Build finished, but expected output not found: $EXPECTED_OUT" >&2
  exit 1
fi
