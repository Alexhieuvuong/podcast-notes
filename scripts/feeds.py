"""
Đọc feeds.txt → danh sách video mới nhất từ các kênh/playlist YouTube (RSS).

Endpoint feeds/videos.xml KHÔNG bị YouTube chặn như timedtext, nên dùng feedparser
giống ai-daily-digest (scripts/sources.py).
"""

import os
from pathlib import Path

import feedparser
import yt_dlp

ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = ROOT / "feeds.txt"
FEED_BASE = "https://www.youtube.com/feeds/videos.xml"


def _read_lines():
    if not FEEDS_FILE.exists():
        return []
    lines = []
    for ln in FEEDS_FILE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            lines.append(ln)
    return lines


def feed_url(line):
    """Dựng URL RSS từ 1 dòng feeds.txt (URL RSS, channel_id, playlist_id, URL kênh/@handle)."""
    if line.startswith("http") and "feeds/videos.xml" in line:
        return line
    if line.startswith("UC") and len(line) >= 22:
        return f"{FEED_BASE}?channel_id={line}"
    if line.startswith(("PL", "UU", "OL")):
        return f"{FEED_BASE}?playlist_id={line}"
    cid = _resolve_channel_id(line)
    return f"{FEED_BASE}?channel_id={cid}" if cid else None


def _resolve_channel_id(line):
    """Lấy channel_id (UC...) từ URL kênh hoặc @handle bằng yt-dlp (xử lý được trang consent EU)."""
    url = line
    if not url.startswith("http"):
        handle = line if line.startswith("@") else "@" + line
        url = f"https://www.youtube.com/{handle}"
    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "playlist_items": "0",  # không liệt kê video → nhanh
    }
    browser = os.environ.get("YT_COOKIES_BROWSER")
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    client = os.environ.get("YDLP_PLAYER_CLIENT") or (None if browser else "android")
    if client:
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None
    cid = info.get("channel_id") or info.get("uploader_id") or info.get("id")
    return cid if isinstance(cid, str) and cid.startswith("UC") else None


def latest_videos():
    """Trả list {video_id, title, url, published, feed} trộn từ mọi feed, mới→cũ.

    Mặc định bỏ qua YouTube Shorts (clip ngắn, không hợp làm ghi chú podcast);
    đặt SKIP_SHORTS=0 để giữ lại.
    """
    skip_shorts = os.environ.get("SKIP_SHORTS", "1") not in ("0", "false", "False")
    vids = []
    for line in _read_lines():
        url = feed_url(line)
        if not url:
            print(f"[feeds] bỏ qua (không resolve được): {line}")
            continue
        d = feedparser.parse(url)
        ftitle = d.feed.get("title", line)
        for e in d.entries:
            vid = getattr(e, "yt_videoid", None)
            if not vid:
                continue
            link = e.get("link", f"https://www.youtube.com/watch?v={vid}")
            if skip_shorts and "/shorts/" in link:
                continue
            # Tác giả tập podcast = tên kênh upload. Với feed playlist, e.author là
            # kênh thật (khác ftitle = tên playlist) nên ưu tiên e.author.
            author = e.get("author") or ftitle
            vids.append({
                "video_id": vid,
                "title": e.get("title", vid),
                "url": link,
                "published": e.get("published", ""),
                "feed": ftitle,
                "author": author,
            })
    vids.sort(key=lambda v: v.get("published", ""), reverse=True)
    return vids
