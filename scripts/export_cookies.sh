#!/bin/bash
# Xuất cookie YouTube từ trình duyệt → file Netscape, để job launchd (chạy NỀN lúc 7h)
# dùng được mà KHÔNG cần Keychain/Full Disk Access.
#
# Chạy TAY (khi đang đăng nhập, có thể bấm cho phép Keychain) — và chạy lại mỗi khi
# cookie hết hạn (thường vài tháng/lần), nếu cron bắt đầu báo 429/không có phụ đề:
#     bash scripts/export_cookies.sh
set -e

ROOT="$HOME/podcast-notes"
PY="$ROOT/.venv/bin/python"

# Đọc YT_COOKIES_BROWSER / YT_COOKIES_FILE từ .env (không source cả file để tránh bất ngờ).
get_env() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'; }
BROWSER="$(get_env YT_COOKIES_BROWSER)"; BROWSER="${BROWSER:-chrome}"
OUT="$(get_env YT_COOKIES_FILE)";        OUT="${OUT:-$ROOT/.cookies.txt}"

if [ ! -x "$PY" ]; then
  echo "❌ Chưa có venv ($PY). Chạy scripts/install_schedule.sh trước." >&2
  exit 1
fi

echo "Xuất cookie từ '$BROWSER' → $OUT"
echo "(macOS có thể hỏi quyền Keychain — bấm Cho phép/Always Allow)"
"$PY" -m yt_dlp --cookies-from-browser "$BROWSER" --cookies "$OUT" \
  --skip-download --simulate --no-warnings \
  "https://www.youtube.com/watch?v=jNQXAC9IVRw" >/dev/null 2>&1 || true

if [ ! -s "$OUT" ]; then
  echo "❌ Không xuất được cookie. Đảm bảo đã đăng nhập YouTube trên '$BROWSER'." >&2
  exit 1
fi
chmod 600 "$OUT"
echo "✓ Đã lưu $(grep -cvE '^#|^$' "$OUT") cookie → $OUT (chmod 600)"
