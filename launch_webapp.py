from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from coupang_reviews.webapp import run_server

_PORT = 8000


def _port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", _PORT)) == 0


def _open_browser() -> None:
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{_PORT}")


if __name__ == "__main__":
    if _port_in_use():
        # Server already running — just open browser
        webbrowser.open(f"http://127.0.0.1:{_PORT}")
    else:
        threading.Thread(target=_open_browser, daemon=True).start()
        run_server()
