"""
Sinh bản tổng hợp văn xuôi (hybrid: diễn giải + trích dẫn nguyên văn kèm timestamp).

2 backend chung 1 interface `synthesize(title, lines, engine)`:
  - claude   : gọi Claude Code CLI headless (gói Pro, không tốn API)  [mặc định]
  - deepseek : gọi DeepSeek API (OpenAI-compatible), có map-reduce cho transcript dài
"""

import os
import shutil
import subprocess
import time

import requests


SYSTEM_PROMPT = """Bạn là một biên tập viên kỳ cựu, viết tiếng Việt tự nhiên, mạch lạc.
Nhiệm vụ: từ transcript một video podcast (mỗi dòng có mốc thời gian dạng [mm:ss]),
viết MỘT bài tổng hợp văn xuôi bằng tiếng Việt — như một bài phân tích tổng hợp,
nhưng GIỮ NGUYÊN ý và giọng của người nói.

Quy tắc bắt buộc:
- Chỉ dùng thông tin CÓ trong transcript. KHÔNG thêm thông tin ngoài, KHÔNG chèn quan điểm
  hay đánh giá của riêng bạn.
- Văn xuôi mạch lạc, chia theo các luận điểm/chủ đề chính. Có tiêu đề (#) và các mục (##).
- KHÔNG trùng lặp: mỗi ý chỉ trình bày một lần; gộp những đoạn người nói lặp lại.
- Với mỗi luận điểm quan trọng, chèn 1 trích dẫn NGUYÊN VĂN ngắn (1–2 câu) kèm mốc thời gian,
  định dạng trên một dòng riêng:  > "trích dẫn nguyên văn" — [mm:ss]
- Nếu là phụ đề tự động (có lỗi nhận dạng), diễn giải cẩn trọng theo nghĩa hợp lý;
  TUYỆT ĐỐI không bịa số liệu, tên riêng.
- Mở đầu bằng 2–3 câu tóm tắt toàn bài. Kết bằng mục "## Ý chính rút gọn" gồm 3–6 gạch đầu dòng.
- CHỈ in ra markdown của bài tổng hợp. KHÔNG viết lời dẫn kiểu "Đây là bản tổng hợp...".
"""

# Prompt cho map-reduce (chỉ dùng khi transcript quá dài với DeepSeek).
_MAP_PROMPT = """Đây là MỘT PHẦN transcript của podcast (có [mm:ss]). Hãy rút ra các luận điểm
chính của phần này dưới dạng gạch đầu dòng tiếng Việt, mỗi luận điểm kèm 1 trích dẫn nguyên văn
ngắn + [mm:ss]. Chỉ dùng thông tin trong phần này, không bịa. Chỉ in ra danh sách gạch đầu dòng."""

_REDUCE_PROMPT = SYSTEM_PROMPT + """

LƯU Ý: Đầu vào dưới đây KHÔNG phải transcript gốc mà là các luận điểm + trích dẫn đã rút ra từ
nhiều phần. Hãy hợp nhất chúng thành một bài tổng hợp hoàn chỉnh theo đúng quy tắc trên,
khử trùng lặp giữa các phần."""


def synthesize(title, lines, engine="claude"):
    engine = (engine or "claude").lower()
    if engine == "claude":
        return _run_claude(title, lines)
    if engine == "deepseek":
        return _run_deepseek(title, lines)
    raise ValueError(f"NOTES_ENGINE không hợp lệ: {engine} (dùng 'claude' hoặc 'deepseek')")


# --------------------------------------------------------------------------- claude

def _claude_bin():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def _run_claude(title, lines):
    model = os.environ.get("NOTES_MODEL", "sonnet")
    prompt = (
        SYSTEM_PROMPT
        + f"\n\nTiêu đề video: {title}\n\n"
        + "Transcript được cung cấp ở phần nội dung bên dưới. "
        + "Viết bài tổng hợp theo đúng các quy tắc trên."
    )
    cmd = [_claude_bin(), "-p", prompt, "--model", model, "--output-format", "text"]
    try:
        proc = subprocess.run(
            cmd, input=lines, capture_output=True, text=True, timeout=900
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Không tìm thấy lệnh `claude`. Cài Claude Code và đăng nhập gói Pro, "
            "hoặc đặt NOTES_ENGINE=deepseek."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude CLI quá thời gian (900s).")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Claude CLI lỗi (exit {proc.returncode}): {(proc.stderr or '').strip()[:500]}"
        )
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError(
            "Claude CLI trả về rỗng. Kiểm tra đã đăng nhập chưa (chạy `claude` rồi `/login`)."
        )
    return out


# --------------------------------------------------------------------------- deepseek

# Ngưỡng chia khúc (~ ký tự). DeepSeek ~64K token; ~3 ký tự/token → ~120K ký tự/khúc cho an toàn.
_MAX_CHARS_SINGLE = 150_000
_CHUNK_CHARS = 110_000


def _run_deepseek(title, lines):
    api_key = os.environ.get("API_KEY")
    if not api_key:
        raise RuntimeError(
            "Thiếu API_KEY cho DeepSeek. Copy API_KEY/API_BASE_URL/API_MODEL từ "
            "~/ai-daily-digest/.env vào ~/podcast-notes/.env."
        )
    base = os.environ.get("API_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("API_MODEL", "deepseek-chat")
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if len(lines) <= _MAX_CHARS_SINGLE:
        user = f"Tiêu đề video: {title}\n\nTranscript:\n{lines}"
        return _ds_call(url, headers, model, SYSTEM_PROMPT, user)

    # map-reduce cho transcript quá dài
    chunks = _split_lines(lines, _CHUNK_CHARS)
    print(f"  [deepseek] transcript dài → chia {len(chunks)} khúc, map-reduce...")
    partials = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  [deepseek] map khúc {i}/{len(chunks)}...")
        partials.append(_ds_call(url, headers, model, _MAP_PROMPT,
                                 f"Tiêu đề: {title}\n\n{chunk}"))
    combined = "\n\n".join(partials)
    print("  [deepseek] reduce...")
    return _ds_call(url, headers, model, _REDUCE_PROMPT,
                    f"Tiêu đề video: {title}\n\nCác luận điểm đã rút:\n{combined}")


def _split_lines(lines, max_chars):
    out, buf, size = [], [], 0
    for ln in lines.split("\n"):
        if size + len(ln) + 1 > max_chars and buf:
            out.append("\n".join(buf))
            buf, size = [], 0
        buf.append(ln)
        size += len(ln) + 1
    if buf:
        out.append("\n".join(buf))
    return out


_MAX_RETRIES = 5
_MAX_BACKOFF = 60


def _ds_call(url, headers, model, system, user):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.6,
        "max_tokens": 8192,
    }
    last = None
    for attempt in range(_MAX_RETRIES):
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        if resp.status_code == 429 or resp.status_code >= 500:
            ra = resp.headers.get("Retry-After")
            try:
                wait = float(ra) if ra else 2 ** attempt
            except ValueError:
                wait = 2 ** attempt
            wait = min(wait, _MAX_BACKOFF) + 1
            last = requests.exceptions.HTTPError(f"{resp.status_code} từ API", response=resp)
            if attempt < _MAX_RETRIES - 1:
                print(f"  [retry] {resp.status_code} — chờ {wait:.0f}s...")
                time.sleep(wait)
                continue
            raise last
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    raise last
