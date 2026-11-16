#!/bin/bash
# Builds "Obsidian Templater.app" (menu bar app) into macos-app/build/

set -euo pipefail
cd "$(dirname "$0")"

REPO="$(cd .. && pwd)"
APP="build/Obsidian Templater.app"
PLIST="$APP/Contents/Info.plist"

swift build -c release

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp .build/release/ObsidianTemplaterBar "$APP/Contents/MacOS/ObsidianTemplaterBar"

cat > "$PLIST" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Obsidian Templater</string>
    <key>CFBundleIdentifier</key>
    <string>local.obsidian-templater.menubar</string>
    <key>CFBundleExecutable</key>
    <string>ObsidianTemplaterBar</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF

# Tell the app where obsidian-templater.py and its venv live
plutil -insert TemplaterRepoPath -string "$REPO" "$PLIST"

codesign --force --sign - "$APP"

echo "Built: $(pwd)/$APP"
