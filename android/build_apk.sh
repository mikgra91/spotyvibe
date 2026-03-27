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

# 2. Copy Python files (preserving directory structure, excluding __pycache__)
for item in app.py config.py core prompts data static templates; do
    if [ -d "$PROJECT_ROOT/$item" ]; then
        # Directory: copy recursively and then remove __pycache__ dirs
        cp -r "$PROJECT_ROOT/$item" "$PYTHON_DEST/"
        find "$PYTHON_DEST/$item" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    else
        cp "$PROJECT_ROOT/$item" "$PYTHON_DEST/"
    fi
done

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
