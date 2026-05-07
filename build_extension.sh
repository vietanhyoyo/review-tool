#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

rm -f extension.zip
cd extension
zip -r ../extension.zip manifest.json popup.html popup.js
cd ..

echo "Đã tạo extension.zip"
echo "Commit và push lên GitHub, bật GitHub Pages từ nhánh main."
