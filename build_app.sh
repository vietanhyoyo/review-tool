#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="CoupangReviewTool"
APP_PATH="$PROJECT_DIR/$APP_NAME.app"
MACOS_DIR="$APP_PATH/Contents/MacOS"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
LAUNCHER="$PROJECT_DIR/launch_webapp.py"

# Verify venv exists
if [ ! -f "$PYTHON_BIN" ]; then
    echo "Lỗi: không tìm thấy $PYTHON_BIN"
    echo "Hãy chạy: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "Đang tạo $APP_NAME.app ..."
rm -rf "$APP_PATH"
mkdir -p "$MACOS_DIR"

# --- Executable (paths hardcoded at build time) ---
cat > "$MACOS_DIR/$APP_NAME" << SCRIPT
#!/bin/bash
exec "$PYTHON_BIN" "$LAUNCHER"
SCRIPT
chmod +x "$MACOS_DIR/$APP_NAME"

# --- Info.plist ---
cat > "$APP_PATH/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.local.coupang-review-tool</string>
    <key>CFBundleName</key>
    <string>Coupang Review Tool</string>
    <key>CFBundleDisplayName</key>
    <string>Coupang Review Tool</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST

echo ""
echo "Tạo thành công: $APP_PATH"
echo ""
echo "Cách dùng:"
echo "  • Double-click CoupangReviewTool.app để chạy"
echo "  • Kéo vào Dock để truy cập nhanh hơn"
echo ""
echo "Để dừng server:"
echo "  kill \$(lsof -ti :8000)"
