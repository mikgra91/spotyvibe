#!/bin/bash
# Build the SpotyVibe Android APK
# Usage: cd android && ./build_apk.sh [debug|release]

set -e

BUILD_TYPE="${1:-debug}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_DEST="$SCRIPT_DIR/app/src/main/python"

echo "=== SpotyVibe Android Build ==="
echo "Build type: $BUILD_TYPE"
echo "Project root: $PROJECT_ROOT"

# 1. Clean and recreate the Python source directory
echo "Copying Python sources..."
rm -rf "$PYTHON_DEST"
mkdir -p "$PYTHON_DEST"

# 2. Copy Python files (preserving directory structure)
cp "$PROJECT_ROOT/app.py" "$PYTHON_DEST/"
cp "$PROJECT_ROOT/config.py" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/core" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/prompts" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/data" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/static" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/templates" "$PYTHON_DEST/"

# Remove __pycache__ directories
find "$PYTHON_DEST" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "Python sources copied to $PYTHON_DEST"

# 3. Build the APK
echo "Building APK..."
cd "$SCRIPT_DIR"

if [ "$BUILD_TYPE" = "release" ]; then
    ./gradlew assembleRelease
    APK_PATH="app/build/outputs/apk/release/app-release.apk"
else
    ./gradlew assembleDebug
    APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
fi

if [ -f "$APK_PATH" ]; then
    echo ""
    echo "=== BUILD SUCCESSFUL ==="
    echo "APK: $SCRIPT_DIR/$APK_PATH"
    echo "Size: $(du -h "$APK_PATH" | cut -f1)"
else
    echo "ERROR: APK not found at expected path"
    exit 1
fi
