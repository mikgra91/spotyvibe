#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# build_dist.sh — Build SpotyVibe wheel and package for distribution
#
# Usage:
#   ./build-tools/build_dist.sh              # builds both macOS + Linux
#   ./build-tools/build_dist.sh macos        # macOS ZIP only
#   ./build-tools/build_dist.sh linux        # Linux tar.gz only
#
# Output:
#   dist/SpotyVibe-macOS.zip
#   dist/SpotyVibe-Linux.tar.gz
#
# Each archive contains only:
#   - spotyvibe-<version>.whl   (the application)
#   - README.txt                (installation guide)
#
# End users install with: pip install spotyvibe-*.whl
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"/..

TARGET="${1:-all}"
DIST_DIR="dist"
STAGE_DIR="$DIST_DIR/.stage"

# ── Build the wheel ──────────────────────────────────────────────────
echo "📦 Building wheel ..."

# Ensure build tool is available
if ! python -m build --version &>/dev/null 2>&1; then
    echo "  Installing 'build' package ..."
    python -m pip install build --quiet
fi

# Clean previous wheel builds
rm -f "$DIST_DIR"/*.whl

python -m build --wheel --outdir "$DIST_DIR"

# Find the built wheel
WHL=$(ls "$DIST_DIR"/*.whl 2>/dev/null | head -1)
if [[ -z "$WHL" ]]; then
    echo "✖ Wheel build failed — no .whl found in $DIST_DIR/"
    exit 1
fi
WHL_NAME=$(basename "$WHL")
echo "✅ Built $WHL_NAME"

# ── macOS archive ────────────────────────────────────────────────────
build_macos() {
    local name="SpotyVibe-macOS"
    local stage="$STAGE_DIR/$name"

    echo ""
    echo "📦 Packaging $name.zip ..."
    rm -rf "$stage"
    mkdir -p "$stage"

    cp "$WHL" "$stage/"
    cp build-tools/README-Install.txt "$stage/README.txt"

    cd "$STAGE_DIR"
    zip -rq "../../$DIST_DIR/$name.zip" "$name"
    cd - > /dev/null

    echo "✅ $DIST_DIR/$name.zip"
}

# ── Linux archive ────────────────────────────────────────────────────
build_linux() {
    local name="SpotyVibe-Linux"
    local stage="$STAGE_DIR/$name"

    echo ""
    echo "📦 Packaging $name.tar.gz ..."
    rm -rf "$stage"
    mkdir -p "$stage"

    cp "$WHL" "$stage/"
    cp build-tools/README-Install.txt "$stage/README.txt"

    cd "$STAGE_DIR"
    tar -czf "../../$DIST_DIR/$name.tar.gz" "$name"
    cd - > /dev/null

    echo "✅ $DIST_DIR/$name.tar.gz"
}

# ── Main ─────────────────────────────────────────────────────────────
case "$TARGET" in
    macos) build_macos ;;
    linux) build_linux ;;
    all)   build_macos; build_linux ;;
    *)     echo "Usage: $0 [macos|linux|all]"; exit 1 ;;
esac

# Clean up staging area
rm -rf "$STAGE_DIR"

echo ""
echo "Done. Archives in $DIST_DIR/"
