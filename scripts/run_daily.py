#!/usr/bin/env python3
"""
Entrypoint cron: chọn video mới từ feeds.txt → tổng hợp (Claude) → gửi email → cập nhật seen.

Chạy tay để test:  ./.venv/bin/python scripts/run_daily.py
Lập lịch: launchd gọi file này (xem com.podcastnotes.daily.plist).
"""

import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

import feeds as F  # noqa: E402
import transcript as T  # noqa: E402
import synthesize as S  # noqa: E402
import state as ST  # noqa: E402
import email_out as E  # noqa: E402
from main import slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main():
    load_dotenv(ROOT / ".env")
    # RESEND_API_KEY: tái dùng từ ai-daily-digest nếu chưa đặt riêng.
    if not os.environ.get("RESEND_API_KEY"):
        alt = Path.home() / "ai-daily-digest" / ".env"
        if alt.exists():
            load_dotenv(alt)
    os.environ.setdefault("NOTES_ENGINE", "claude")
    engine = os.environ.get("NOTES_ENGINE", "claude")
    max_new = int(os.environ.get("MAX_NEW", "2"))

    seen = ST.load_seen()
    try:
        vids = F.latest_videos()
    except Exception as e:
        log(f"Lỗi đọc feeds: {e}")
        return 1
    new = [v for v in vids if v["video_id"] not in seen]
    if not new:
        log("Không có video mới.")
        return 0

    todo = new[:max_new]  # mới→cũ: ưu tiên video mới nhất, tối đa MAX_NEW
    log(f"{len(new)} video mới; xử lý {len(todo)} (MAX_NEW={max_new}, engine={engine}).")

    if "--dry-run" in sys.argv:
        for v in todo:
            log(f"  [dry-run] sẽ xử lý: {v['title']}  ({v['url']})")
        return 0

    for v in todo:
        vid, title, url = v["video_id"], v["title"], v["url"]
        log(f"→ {title}  ({url})")
        try:
            _, _segs, lines = T.fetch(url)
        except T.NoTranscript as e:
            msg = str(e)
            if "429" in msg:
                log(f"  429 từ YouTube — để lại, thử lần chạy sau.")
                continue
            log("  Không có phụ đề — đánh dấu no_captions (khỏi thử lại).")
            seen[vid] = {"title": title, "date": datetime.date.today().isoformat(),
                         "status": "no_captions"}
            ST.save_seen(seen)
            continue
        except Exception as e:
            log(f"  Lỗi transcript: {e} — bỏ qua lần này.")
            continue

        try:
            md = S.synthesize(title, lines, engine=engine)
        except Exception as e:
            log(f"  Lỗi tổng hợp: {e} — bỏ qua lần này.")
            continue

        author = v.get("author") or v["feed"]
        date = datetime.date.today().isoformat()
        out = ROOT / "notes" / f"{date}-{slugify(title)}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        header = f"> Tác giả: {author}  ·  Nguồn: {url}  ·  Ngày: {date}\n\n---\n\n"
        out.write_text(header + md.strip() + "\n", encoding="utf-8")
        log(f"  ✓ Lưu {out.name}")

        # Cho biết rõ tác giả ngay trong tiêu đề + đầu thân email.
        email_body = f"**🎙 Tác giả:** {author}  \n**▶️ Nguồn:** {url}\n\n---\n\n" + md
        E.send_email(f"🎧 [{author}] {title}", email_body)

        seen[vid] = {"title": title, "date": date, "status": "done"}
        ST.save_seen(seen)

    # Đồng bộ sang Obsidian vault để đọc lúc rảnh (idempotent; lỗi vault không làm hỏng run).
    try:
        import obsidian_sync as OB  # noqa: E402
        open_app = os.environ.get("OBSIDIAN_OPEN", "1") != "0"
        OB.sync_to_vault(open_app=open_app, log=log)
    except Exception as e:
        log(f"Obsidian sync lỗi (bỏ qua): {e}")

    log("Xong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
