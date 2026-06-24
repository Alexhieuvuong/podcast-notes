"""
Lấy transcript YouTube có timestamp — qua yt-dlp (bền hơn youtube-transcript-api,
vốn hay bị YouTube chặn ngay cả từ IP nhà).

- Dùng player client `android` (env YDLP_PLAYER_CLIENT để đổi) — client `web` mặc định
  thường bị YouTube giấu caption tracks.
- Ưu tiên phụ đề người tạo (vi → en), rồi tự sinh (vi → en), rồi bất kỳ.
- Để yt-dlp TẢI file json3 (request đúng cách); tải URL phụ đề bằng requests bị trả rỗng.
- Trả về: (title, segments, lines) với `lines` là chuỗi "[mm:ss] text" mỗi dòng (~15s/block).
"""

import glob
import json
import os
import shutil
import tempfile
import time

import yt_dlp


class NoTranscript(Exception):
    """Không tìm/không tải được transcript cho video."""


def _base_opts():
    """Opts chung cho yt-dlp, đọc env tại thời điểm gọi (sau khi .env đã nạp).

    YT_COOKIES_BROWSER (chrome|safari|firefox|brave|edge): dùng cookie trình duyệt
    đã đăng nhập YouTube → request có xác thực, tránh 429/chặn IP ẩn danh.
    """
    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    browser = os.environ.get("YT_COOKIES_BROWSER")
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    # Client: CÓ cookie → client mặc định (web đăng nhập, trả caption tốt nhất);
    # KHÔNG cookie → android (trả caption khi ẩn danh). Ép tay qua YDLP_PLAYER_CLIENT.
    client = os.environ.get("YDLP_PLAYER_CLIENT") or (None if browser else "android")
    if client:
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    return opts


def _ts(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _probe(url):
    """extract_info không tải gì — lấy title + danh sách phụ đề."""
    try:
        with yt_dlp.YoutubeDL(_base_opts()) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise NoTranscript(f"Không lấy được thông tin video (yt-dlp): {e}")


def _choose_lang(info):
    """Trả (lang, is_auto). Ưu tiên vi/en thủ công, rồi vi/en tự sinh, rồi bất kỳ."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    for lang in ("vi", "en"):
        if lang in manual:
            return lang, False
    for lang in ("vi", "en"):
        if lang in auto:
            return lang, True
    if manual:
        return next(iter(manual)), False
    if auto:
        return next(iter(auto)), True
    return None, None


def _download_sub(url, lang, is_auto, outdir, retries=3):
    opts = dict(_base_opts())
    opts.update({
        "writesubtitles": not is_auto,
        "writeautomaticsub": is_auto,
        "subtitleslangs": [lang],
        "subtitlesformat": "json3",
        "outtmpl": os.path.join(outdir, "%(id)s.%(ext)s"),
    })
    last = None
    for attempt in range(retries):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
            files = glob.glob(os.path.join(outdir, "*.json3"))
            if files:
                return files[0]
            last = "yt-dlp không ghi ra file json3."
        except yt_dlp.utils.DownloadError as e:
            last = str(e)
            if "429" in last and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  [transcript] 429 từ YouTube — chờ {wait}s rồi thử lại...")
                time.sleep(wait)
                continue
            break
    raise NoTranscript(
        f"Không tải được phụ đề ({lang}). {last}\n"
        "   Nếu là 429/too many requests: chờ vài phút rồi chạy lại."
    )


def _parse_json3(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    segments = []
    for ev in data.get("events", []):
        if not ev.get("segs"):
            continue
        text = "".join(s.get("utf8", "") for s in ev["segs"]).replace("\n", " ").strip()
        if not text:
            continue
        segments.append({"start": ev.get("tStartMs", 0) / 1000.0, "text": text})
    return segments


def _format_lines(segments, block=15.0):
    """Gộp segment thành block ~`block` giây: '[mm:ss] văn bản gộp'."""
    out, buf, bstart = [], [], None
    for seg in segments:
        text = seg["text"]
        if not text:
            continue
        start = seg["start"]
        if bstart is None:
            bstart = start
        buf.append(text)
        if start - bstart >= block:
            out.append(f"[{_ts(bstart)}] {' '.join(buf)}")
            buf, bstart = [], None
    if buf:
        out.append(f"[{_ts(bstart or 0)}] {' '.join(buf)}")
    return "\n".join(out)


def fetch(url):
    """Trả về (title, segments, lines)."""
    info = _probe(url)
    title = info.get("title") or info.get("id") or "podcast"
    lang, is_auto = _choose_lang(info)
    if lang is None:
        raise NoTranscript("Video không có phụ đề (kể cả tự động).")
    outdir = tempfile.mkdtemp(prefix="ptn_")
    try:
        path = _download_sub(url, lang, is_auto, outdir)
        segments = _parse_json3(path)
    finally:
        shutil.rmtree(outdir, ignore_errors=True)
    if not segments:
        raise NoTranscript("Phụ đề rỗng sau khi parse.")
    lines = _format_lines(segments)
    return title, segments, lines
