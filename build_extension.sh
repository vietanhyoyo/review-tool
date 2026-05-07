#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

rm -f web/extension.zip
cd extension
zip -r ../web/extension.zip manifest.json popup.html popup.js
cd ..

echo "Đã tạo web/extension.zip"
echo "Deploy lên Vercel: npx vercel --prod"
