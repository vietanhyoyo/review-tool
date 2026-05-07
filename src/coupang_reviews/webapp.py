from __future__ import annotations

import json
import shutil
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .scraper import scrape_reviews_from_cdp_to_excel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"

_CHROME_CANDIDATES = [
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    # Linux
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_chrome() -> str | None:
    for candidate in _CHROME_CANDIDATES:
        path = Path(candidate)
        if path.is_absolute():
            if path.exists():
                return str(path)
        else:
            if shutil.which(candidate):
                return candidate
    return None


def launch_chrome_with_cdp(port: int = 9222) -> dict[str, object]:
    chrome = find_chrome()
    if not chrome:
        return {"ok": False, "error": "Không tìm thấy Google Chrome trên máy."}

    # Use a dedicated profile directory so Chrome starts as a NEW process
    # even when the user's regular Chrome is already open.
    profile_dir = PROJECT_ROOT / ".chrome-cdp-profile"
    profile_dir.mkdir(exist_ok=True)

    try:
        subprocess.Popen(
            [
                chrome,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "message": f"Đã mở Chrome (cửa sổ riêng) với CDP trên cổng {port}."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Web app running at http://{host}:{port}")
    print("Connect Chrome with remote debugging before scraping.")
    server.serve_forever()


class RequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._add_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if self.path == "/app.js":
            self._serve_file(WEB_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if self.path == "/styles.css":
            self._serve_file(WEB_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if self.path == "/api/check-chrome":
            self._send_json(check_chrome_debug_endpoint(DEFAULT_CDP_URL))
            return
        if self.path == "/api/launch-chrome":
            self._send_json(launch_chrome_with_cdp())
            return
        if self.path.startswith("/api/download"):
            self._handle_download()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_download(self) -> None:
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        file_rel = query.get("file", [""])[0].strip()
        if not file_rel:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        file_path = (PROJECT_ROOT / file_rel).resolve()
        # Security: must stay within project root
        try:
            file_path.relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = file_path.read_bytes()
        filename = file_path.name
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.send_header("Content-Length", str(len(content)))
        self.send_header(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if self.path != "/api/scrape":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        payload = self._read_json_body()
        if payload is None:
            return

        product_url = str(payload.get("url", "")).strip()
        output = str(payload.get("output", "output/coupang_reviews.xlsx")).strip()
        cdp_url = str(payload.get("cdpUrl", DEFAULT_CDP_URL)).strip() or DEFAULT_CDP_URL
        try:
            pages = int(payload.get("pages", 5))
        except (TypeError, ValueError):
            self._send_json(
                {"ok": False, "error": "Pages must be an integer."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if not product_url.startswith("http"):
            self._send_json(
                {"ok": False, "error": "A valid Coupang URL is required."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        output_path = PROJECT_ROOT / output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            row_count = scrape_reviews_from_cdp_to_excel(
                product_url=product_url,
                output_path=output_path,
                cdp_url=cdp_url,
                max_pages=pages,
            )
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json(
            {
                "ok": True,
                "rows": row_count,
                "output": str(output_path.relative_to(PROJECT_ROOT)),
            }
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict[str, object] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            return json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_json(
                {"ok": False, "error": "Invalid JSON body."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return None

    def _add_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(content)


def check_chrome_debug_endpoint(cdp_url: str) -> dict[str, object]:
    version_url = f"{cdp_url.rstrip('/')}/json/version"
    try:
        with urlopen(version_url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "ok": True,
                "browser": payload.get("Browser", ""),
                "webSocketDebuggerUrl": payload.get("webSocketDebuggerUrl", ""),
            }
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": (
                "Chrome remote debugging is not reachable. "
                "Start Chrome with --remote-debugging-port=9222. "
                f"Details: {exc}"
            ),
        }
