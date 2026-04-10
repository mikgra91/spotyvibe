#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# build_dist.sh — Package SpotyVibe source distributions for macOS/Linux
#
# Usage:
#   ./build-tools/build_dist.sh              # builds both macOS + Linux
#   ./build-tools/build_dist.sh macos        # macOS only
#   ./build-tools/build_dist.sh linux        # Linux only
#
# Output:
#   dist/SpotyVibe-macOS.zip
#   dist/SpotyVibe-Linux.tar.gz
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"/..


TARGET="${1:-all}"
DIST_DIR="dist"
STAGE_DIR="$DIST_DIR/.stage"

mkdir -p "$DIST_DIR"

# ── Files to include in both archives ──────────────────────────────
# Runtime sources only — no tests, no Android, no build scaffolding,
# no desktop-only files, no dev docs.
INCLUDE_FILES=(
    app.py
    config.py
    version.py
    requirements-core.txt
    build-tools/start.sh
    data/music_profile.json
)

INCLUDE_DIRS=(
    core/src
    frontend/templates
    frontend/static
    prompts
)

# ── Helper: populate staging directory ─────────────────────────────
stage_common() {
    local dest="$1"
    rm -rf "$dest"
    mkdir -p "$dest"

    for f in "${INCLUDE_FILES[@]}"; do
        mkdir -p "$dest/$(dirname "$f")"
        cp "$f" "$dest/$f"
    done

    for d in "${INCLUDE_DIRS[@]}"; do
        mkdir -p "$dest/$d"
        cp -r "$d"/. "$dest/$d"/
    done

    # Remove __pycache__ dirs that may have been copied
    find "$dest" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
}

# ── macOS archive ──────────────────────────────────────────────────
build_macos() {
    local name="SpotyVibe-macOS"
    local stage="$STAGE_DIR/$name"

    echo "📦 Building $name.zip ..."
    stage_common "$stage"

    # macOS wrapper at root level
    cp SpotyVibe.command "$stage/"

    # Platform-specific README
    cp build-tools/README-macOS.txt "$stage/README.txt"

    # Create ZIP (from inside stage dir so paths are relative)
    cd "$STAGE_DIR"
    zip -rq "../../$DIST_DIR/$name.zip" "$name"
    cd - > /dev/null

    echo "✅ $DIST_DIR/$name.zip"
}

# ── Linux archive ──────────────────────────────────────────────────
build_linux() {
    local name="SpotyVibe-Linux"
    local stage="$STAGE_DIR/$name"

    echo "📦 Building $name.tar.gz ..."
    stage_common "$stage"

    # Linux wrapper at root level
    cp start.sh "$stage/"

    # Platform-specific README
    cp build-tools/README-Linux.txt "$stage/README.txt"

    # Create tar.gz (from inside stage dir so paths are relative)
    cd "$STAGE_DIR"
    tar -czf "../../$DIST_DIR/$name.tar.gz" "$name"
    cd - > /dev/null

    echo "✅ $DIST_DIR/$name.tar.gz"
}

# ── Main ───────────────────────────────────────────────────────────
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

