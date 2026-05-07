# Coupang Review Scraper

Project Python + Playwright + pandas để lấy đánh giá sản phẩm từ Coupang và xuất ra file Excel.

## Yêu cầu

- Python 3.9+
- Cài package:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Cách chạy

```bash
python3 run.py \
  --url "https://www.coupang.com/vp/products/8641502931?vendorItemId=91016320793&sourceType=HOME_PERSONALIZED_ADS&searchId=feed-b738d15f15724beeba85ad7c10869cba-3.33.14%3Apersonalized_ads&clickEventId=e6904290-49dd-11f1-b463-9db4dff78bef" \
  --pages 5 \
  --output output/coupang_reviews.xlsx
```

## Giao diện HTML dùng Chrome thật

Nếu bạn mở được Coupang trên Google Chrome thường nhưng Playwright bị chặn, hãy dùng web app local để Python bám vào Chrome thật qua remote debugging:

1. Đóng toàn bộ cửa sổ Google Chrome đang chạy.
2. Mở lại Chrome bằng lệnh:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

3. Chrome sẽ mở bằng profile thật của bạn, nên session/cookie đang có sẽ được giữ lại. Nếu cần, đăng nhập Coupang trong cửa sổ đó và xác nhận truy cập được trang sản phẩm.
4. Chạy web app local:

```bash
python3 launch_webapp.py
```

5. Mở `http://127.0.0.1:8000`, nhập link Coupang rồi bấm scrape.

Web app sẽ dùng session/cookie của chính cửa sổ Chrome đang mở qua cổng CDP `9222`, thay vì tạo một trình duyệt Playwright trắng.

## Tạo session đăng nhập

Nếu Coupang chặn truy cập từ IP/session hiện tại, tạo `storage-state.json` bằng cách tự đăng nhập trong trình duyệt Playwright:

```bash
python3 save_storage_state.py --output storage-state.json
```

Nếu bạn cần đi qua proxy ngay từ bước đăng nhập:

```bash
python3 save_storage_state.py \
  --output storage-state.json \
  --proxy-server "http://host:port"
```

Sau khi lưu được session, dùng lại file đó khi scrape:

```bash
python3 run.py \
  --url "..." \
  --pages 5 \
  --output output/coupang_reviews.xlsx \
  --storage-state storage-state.json
```

Nếu Coupang chỉ cho truy cập từ session / IP hợp lệ, có thể chạy thêm:

```bash
python3 run.py \
  --url "..." \
  --pages 5 \
  --output output/coupang_reviews.xlsx \
  --proxy-server "http://host:port" \
  --storage-state storage-state.json
```

## Output

File Excel sẽ chứa các cột:

- `product_url`
- `review_id`
- `author`
- `rating`
- `headline`
- `content`
- `option_text`
- `survey_text`
- `helpful_count`
- `review_date`
- `collected_at`
- `page_number`

## Lưu ý

- Coupang có thể thay đổi HTML hoặc chặn scraping theo IP / vùng / tần suất truy cập.
- Trên môi trường hiện tại, Coupang đang trả `Access Denied` từ Akamai trước khi render trang sản phẩm. Khi gặp trường hợp này, bạn cần chạy script từ IP truy cập được Coupang hoặc truyền session/proxy phù hợp.
- Script ưu tiên selector theo text và cấu trúc review phổ biến; nếu Coupang đổi giao diện, cần cập nhật selector.
- Nếu trang review không tải đầy đủ, chạy với `--headful` để quan sát trình duyệt thực.
