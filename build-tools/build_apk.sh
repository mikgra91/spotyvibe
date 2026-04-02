#!/bin/bash
# Build the SpotyVibe Android APK
#
# Usage (run from repo root):
#   ./build-tools/build_apk.sh [debug|release]

set -e

BUILD_TYPE="${1:-debug}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ANDROID_DIR="$PROJECT_ROOT/android"
PYTHON_DEST="$ANDROID_DIR/app/src/main/python"

echo "=== SpotyVibe Android Build ==="
echo "Build type: $BUILD_TYPE"
echo "Project root: $PROJECT_ROOT"
echo "Android dir: $ANDROID_DIR"

# 0. Clean previous build artifacts/caches from earlier runs
echo "Cleaning previous build artifacts..."

(
  cd "$ANDROID_DIR"

  # Stop any running Gradle daemons (ignore errors if none are running)
  ./gradlew --stop >/dev/null 2>&1 || true

  # Clean via Gradle (removes prior build outputs)
  ./gradlew clean

  # Extra cleanup for commonly-stale build fragments (safe to ignore if missing)
  rm -rf \
    "$ANDROID_DIR/app/build" \
    "$ANDROID_DIR/build" \
    "$ANDROID_DIR/.gradle" \
    "$ANDROID_DIR/app/.cxx" \
    "$ANDROID_DIR/app/.externalNativeBuild" \
    2>/dev/null || true
)

# 1. Clean and recreate the Python source directory

echo "Copying Python sources..."
rm -rf "$PYTHON_DEST"
mkdir -p "$PYTHON_DEST"

# 2. Copy Python files (preserving directory structure, excluding __pycache__)
for item in app.py spotyvibe_bootstrap.py config.py core prompts data frontend documentation; do
  if [ -d "$PROJECT_ROOT/$item" ]; then
    cp -r "$PROJECT_ROOT/$item" "$PYTHON_DEST/"
    find "$PYTHON_DEST/$item" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
  elif [ -f "$PROJECT_ROOT/$item" ]; then
    cp "$PROJECT_ROOT/$item" "$PYTHON_DEST/"
  fi
done

echo "Python sources copied to $PYTHON_DEST"

# 3. Build the APK

echo "Building APK..."
(
  cd "$ANDROID_DIR"

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
    echo "APK: $ANDROID_DIR/$APK_PATH"
    echo "Size: $(du -h "$APK_PATH" | cut -f1)"
  else
    echo "ERROR: APK not found at expected path"
    exit 1
  fi
)
