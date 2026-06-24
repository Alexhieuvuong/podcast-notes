#!/usr/bin/env python3
"""
Podcast → ghi chú tổng hợp hằng ngày.

Dùng:
    python scripts/main.py <youtube-url>

Engine chọn qua biến môi trường NOTES_ENGINE (claude | deepseek), mặc định claude.
"""

import datetime
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

import transcript as T  # noqa: E402
import synthesize as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def slugify(text, maxlen=60):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:maxlen].rstrip("-")) or "podcast"


def main():
    import os

    if len(sys.argv) < 2:
        print("Dùng: python scripts/main.py <youtube-url>")
        return 2
    url = sys.argv[1]

    load_dotenv(ROOT / ".env")
    engine = os.environ.get("NOTES_ENGINE", "claude").lower()
    # Tái dùng key DeepSeek từ ai-daily-digest nếu thiếu.
    if engine == "deepseek" and not os.environ.get("API_KEY"):
        alt = Path.home() / "ai-daily-digest" / ".env"
        if alt.exists():
            load_dotenv(alt)

    print("Đang lấy transcript...")
    try:
        title, segments, lines = T.fetch(url)
    except T.NoTranscript as e:
        print(f"❌ {e}")
        print("   (v1 chỉ hỗ trợ video có phụ đề. Bật fallback Whisper trong requirements.txt nếu cần.)")
        return 1
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    print(f"  ✓ {title} — {len(segments)} đoạn, {len(lines):,} ký tự transcript")

    print(f"Đang tổng hợp (engine={engine})...")
    try:
        md = S.synthesize(title, lines, engine=engine)
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1

    date = datetime.date.today().isoformat()
    out = ROOT / "notes" / f"{date}-{slugify(title)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = f"> Nguồn: {url}  ·  Ngày: {date}  ·  Engine: {engine}\n\n---\n\n"
    out.write_text(header + md.strip() + "\n", encoding="utf-8")
    print(f"\n✅ Đã lưu: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
