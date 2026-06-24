#!/usr/bin/env python3
"""
Đồng bộ ghi chú podcast (notes/*.md) sang Obsidian vault để đọc lúc rảnh.

- Chuyển header blockquote (đã "trôi" qua nhiều phiên bản: Nguồn/Kênh/Tác giả/Ngày/Engine)
  thành YAML frontmatter sạch (title/date/channel/source/tags) cho dễ đọc & tìm.
- Ghi vào   <vault>/<subdir>/   (mặc định: ~/Documents/Obsidian Vault/Podcasts).
- Dựng lại  _Index.md  = danh sách nghe, mới nhất trước.
- Sau khi ghi, mở Obsidian ở chế độ nền (open -ga) để Obsidian Sync đẩy lên tài khoản.

Chạy tay:   ./.venv/bin/python scripts/obsidian_sync.py            (backfill tất cả notes/)
            ./.venv/bin/python scripts/obsidian_sync.py --dry-run  (chỉ liệt kê)
            ./.venv/bin/python scripts/obsidian_sync.py --no-open  (không mở Obsidian)

Cấu hình qua env (hoặc .env):
    OBSIDIAN_VAULT   đường dẫn vault   (mặc định: ~/Documents/Obsidian Vault)
    OBSIDIAN_SUBDIR  thư mục con        (mặc định: Podcasts)
    OBSIDIAN_OPEN    "0" để không tự mở Obsidian (mặc định: mở)
"""

import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "notes"

DEFAULT_VAULT = Path.home() / "Documents" / "Obsidian Vault"
DEFAULT_SUBDIR = "Podcasts"
INDEX_NAME = "_Index.md"

# Nhãn header tiếng Việt → khoá chuẩn. So khớp không phân biệt hoa/thường.
LABEL_MAP = {
    "nguồn": "source",
    "kênh": "channel",
    "tác giả": "channel",   # bản run_daily.py cũ dùng "Tác giả" thay cho "Kênh"
    "ngày": "date",
    # "engine" cố tình bỏ qua.
}

DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def yaml_str(value: str) -> str:
    """Bọc một chuỗi thành scalar YAML an toàn (double-quoted)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def parse_note(path: Path) -> dict:
    """Tách 1 file notes/*.md thành metadata + body.

    Trả về dict: {title, date, channel, source, body}. Khoan dung với header trôi:
    nếu thiếu trường nào thì suy ra từ tên file / nội dung, không bao giờ ném lỗi.
    """
    text = path.read_text(encoding="utf-8")

    # Header (blockquote) nằm trước dấu ngăn "\n---\n" đầu tiên; phần còn lại là body.
    parts = text.split("\n---\n", 1)
    if len(parts) == 2:
        header_block, body = parts[0], parts[1].lstrip("\n")
    else:
        header_block, body = "", text  # không có header → coi tất cả là body

    meta = {"source": "", "channel": "", "date": ""}
    for line in header_block.splitlines():
        line = line.strip()
        if not line.startswith(">"):
            continue
        line = line.lstrip(">").strip()
        for chunk in line.split("·"):
            if ":" not in chunk:
                continue
            label, _, val = chunk.partition(":")
            key = LABEL_MAP.get(label.strip().lower())
            if key and val.strip():
                meta.setdefault(key, "")
                # Không ghi đè giá trị đã có (ưu tiên "Kênh" hơn "Tác giả" nếu cùng map).
                if not meta.get(key):
                    meta[key] = val.strip()

    # Tiêu đề: dòng H1 đầu tiên trong body; nếu không có thì dựng từ tên file.
    title = ""
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    if not title:
        stem = DATE_PREFIX_RE.sub("", path.stem)
        title = stem.replace("-", " ").strip().capitalize() or path.stem

    # Ngày: ưu tiên header, rồi tiền tố tên file, cuối cùng là mtime.
    if not meta["date"]:
        m = DATE_PREFIX_RE.match(path.name)
        if m:
            meta["date"] = m.group(1)
        else:
            meta["date"] = datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()

    return {
        "title": title,
        "date": meta["date"],
        "channel": meta["channel"],
        "source": meta["source"],
        "body": body.rstrip() + "\n",
    }


def render_vault_note(meta: dict) -> str:
    """Dựng nội dung file trong vault: frontmatter + dòng nguồn + body gốc."""
    fm = ["---", f"title: {yaml_str(meta['title'])}"]
    if meta["date"]:
        fm.append(f"date: {meta['date']}")
    if meta["channel"]:
        fm.append(f"channel: {yaml_str(meta['channel'])}")
    if meta["source"]:
        fm.append(f"source: {meta['source']}")
    fm.append("tags: [podcast]")
    fm.append("---")

    # Dòng nguồn dễ bấm khi đọc.
    src_bits = []
    if meta["source"]:
        src_bits.append(f"🎧 [Nghe trên YouTube]({meta['source']})")
    if meta["channel"]:
        src_bits.append(meta["channel"])
    if meta["date"]:
        src_bits.append(meta["date"])
    src_line = " · ".join(src_bits)

    out = "\n".join(fm) + "\n"
    if src_line:
        out += "\n" + src_line + "\n"
    out += "\n" + meta["body"]
    return out


def render_index(items: list[dict]) -> str:
    """Dựng _Index.md = danh sách nghe, mới nhất trước."""
    items = sorted(items, key=lambda x: (x["date"], x["stem"]), reverse=True)
    today = datetime.date.today().isoformat()
    lines = [
        "---",
        "title: Podcasts — Danh sách nghe",
        "tags: [moc]",
        f"updated: {today}",
        "---",
        "",
        "# 🎧 Podcasts — Danh sách nghe",
        "",
        f"Tổng hợp {len(items)} ghi chú podcast, mới nhất trước. "
        "Tự sinh bởi `obsidian_sync.py` — đừng sửa tay.",
        "",
    ]
    for it in items:
        alias = it["title"].replace("|", " ").replace("]", " ")
        meta = " — ".join(b for b in (it["channel"], it["date"]) if b)
        suffix = f" — {meta}" if meta else ""
        lines.append(f"- [[{it['stem']}|{alias}]]{suffix}")
    return "\n".join(lines) + "\n"


def _open_obsidian(log) -> None:
    """Mở Obsidian ở chế độ nền để Sync đẩy file mới lên tài khoản."""
    try:
        subprocess.run(["open", "-ga", "Obsidian"], check=False)
        log("  ↻ Đã kích hoạt Obsidian (nền) để Sync.")
    except Exception as e:
        log(f"  (không mở được Obsidian: {e})")


def sync_to_vault(open_app: bool = True, dry_run: bool = False, log=print) -> dict:
    """Đồng bộ toàn bộ notes/*.md sang vault. Idempotent: chỉ ghi file mới/đổi.

    Trả về {"written": int, "skipped": int, "total": int}.
    """
    vault = Path(os.environ.get("OBSIDIAN_VAULT", str(DEFAULT_VAULT))).expanduser()
    subdir = os.environ.get("OBSIDIAN_SUBDIR", DEFAULT_SUBDIR)
    dest_dir = vault / subdir

    if not vault.exists():
        raise FileNotFoundError(f"Không thấy Obsidian vault: {vault} (đặt OBSIDIAN_VAULT?)")

    note_files = sorted(NOTES_DIR.glob("*.md")) if NOTES_DIR.exists() else []
    if not note_files:
        log("Không có ghi chú nào trong notes/.")
        return {"written": 0, "skipped": 0, "total": 0}

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    written = skipped = 0
    index_items = []
    for nf in note_files:
        meta = parse_note(nf)
        index_items.append({
            "stem": nf.stem,
            "title": meta["title"],
            "channel": meta["channel"],
            "date": meta["date"],
        })
        target = dest_dir / nf.name
        content = render_vault_note(meta)

        if dry_run:
            state = "MỚI" if not target.exists() else "cập nhật"
            log(f"  [dry-run] {state}: {subdir}/{nf.name}  «{meta['title']}»")
            continue

        # Idempotent: bỏ qua nếu nội dung không đổi.
        if target.exists() and target.read_text(encoding="utf-8") == content:
            skipped += 1
            continue
        target.write_text(content, encoding="utf-8")
        written += 1
        log(f"  ✓ {subdir}/{nf.name}")

    # Luôn dựng lại index để phản ánh đúng vault.
    if not dry_run:
        (dest_dir / INDEX_NAME).write_text(render_index(index_items), encoding="utf-8")
        if written and open_app:
            _open_obsidian(log)

    log(f"Obsidian: {written} mới/đổi, {skipped} giữ nguyên, {len(note_files)} tổng → {dest_dir}")
    return {"written": written, "skipped": skipped, "total": len(note_files)}


def main() -> int:
    load_dotenv(ROOT / ".env")
    dry_run = "--dry-run" in sys.argv
    open_app = "--no-open" not in sys.argv and os.environ.get("OBSIDIAN_OPEN", "1") != "0"
    try:
        sync_to_vault(open_app=open_app, dry_run=dry_run)
    except Exception as e:
        print(f"❌ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
