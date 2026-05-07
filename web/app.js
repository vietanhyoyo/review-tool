const launchButton = document.getElementById("launchChromeButton");
const checkButton = document.getElementById("checkChromeButton");
const submitButton = document.getElementById("submitButton");
const chromeStatus = document.getElementById("chromeStatus");
const result = document.getElementById("result");
const downloadLink = document.getElementById("downloadLink");
const form = document.getElementById("scrapeForm");

// When served from Vercel (not localhost), call the local Python server directly
const isLocal = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const API = isLocal ? "" : "http://localhost:8000";

function setStatus(message, kind) {
  chromeStatus.textContent = message;
  chromeStatus.className = `status ${kind}`;
}

async function launchChrome() {
  setStatus("Đang mở Chrome...", "loading");
  launchButton.disabled = true;
  try {
    const response = await fetch(`${API}/api/launch-chrome`);
    const payload = await response.json();
    if (!payload.ok) {
      setStatus("Không mở được Chrome", "error");
      result.textContent = payload.error;
      return;
    }
    setStatus("Chrome đang khởi động...", "loading");
    result.textContent = payload.message + "\nĐăng nhập Coupang trong cửa sổ Chrome, rồi bấm Kiểm tra kết nối.";
    // Auto-check connection after 3s
    setTimeout(() => void checkChrome(), 3000);
  } catch (error) {
    setStatus("Lỗi", "error");
    result.textContent = String(error);
  } finally {
    launchButton.disabled = false;
  }
}

async function checkChrome() {
  setStatus("Đang kiểm tra...", "loading");
  try {
    const response = await fetch(`${API}/api/check-chrome`);
    const payload = await response.json();
    if (!payload.ok) {
      setStatus("Không kết nối được", "error");
      result.textContent = payload.error;
      submitButton.disabled = true;
      return;
    }
    setStatus("Đã kết nối ✓", "success");
    result.textContent = `Chrome sẵn sàng: ${payload.browser}`;
    submitButton.disabled = false;
  } catch (error) {
    setStatus("Lỗi kết nối", "error");
    result.textContent = String(error);
    submitButton.disabled = true;
  }
}

launchButton.addEventListener("click", () => void launchChrome());
checkButton.addEventListener("click", () => void checkChrome());

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  result.textContent = "Đang scrape. Giữ nguyên cửa sổ Chrome đã đăng nhập Coupang.";

  const payload = {
    url: document.getElementById("url").value.trim(),
    pages: Number(document.getElementById("pages").value),
    output: document.getElementById("output").value.trim(),
    cdpUrl: document.getElementById("cdpUrl").value.trim(),
  };

  downloadLink.hidden = true;

  try {
    const response = await fetch(`${API}/api/scrape`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!data.ok) {
      result.textContent = `Lỗi: ${data.error}`;
      return;
    }

    result.textContent = `Hoàn tất. Đã lưu ${data.rows} review vào ${data.output}`;
    downloadLink.href = `${API}/api/download?file=${encodeURIComponent(data.output)}`;
    downloadLink.textContent = `Tải file Excel (${data.rows} review)`;
    downloadLink.download = data.output.split("/").pop();
    downloadLink.hidden = false;
  } catch (error) {
    result.textContent = `Lỗi: ${String(error)}`;
  } finally {
    submitButton.disabled = false;
  }
});
