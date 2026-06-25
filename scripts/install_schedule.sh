#!/bin/bash
# Lập lịch chạy podcast-notes hằng ngày trên Mac:
#   - launchd (LaunchAgent) chạy job lúc 07:00
#   - pmset đánh thức máy lúc 06:55 (cần sudo; chỉ thức từ SLEEP, không từ tắt nguồn; nên cắm điện)
set -e

ROOT="$HOME/podcast-notes"
PLIST="com.podcastnotes.daily.plist"
DEST="$HOME/Library/LaunchAgents/$PLIST"

# --- Bootstrap phụ thuộc (đảm bảo cron lấy được transcript) ---
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

# 1) venv + deps Python (requirements.txt đã gồm curl_cffi + bgutil plugin)
if [ ! -x "$PY" ]; then
  echo "Tạo virtualenv..."
  python3 -m venv "$VENV"
fi
echo "Cài/cập nhật deps Python..."
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r "$ROOT/requirements.txt"

# 2) bgutil PO-token generator (Node, script mode) — cần để vượt rào phụ đề YouTube
BG_TAG="1.1.0"   # PHẢI khớp bgutil-ytdlp-pot-provider trong requirements.txt
BG_DIR="$HOME/bgutil-ytdlp-pot-provider"
BG_GEN="$BG_DIR/server/build/generate_once.js"
if [ ! -f "$BG_GEN" ]; then
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "⚠️  Cần Node.js + npm để build bgutil PO-token generator. Cài Node rồi chạy lại." >&2
    exit 1
  fi
  echo "Clone & build bgutil PO-token generator ($BG_TAG)..."
  rm -rf "$BG_DIR"
  git clone --quiet --depth 1 --branch "$BG_TAG" \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$BG_DIR"
  ( cd "$BG_DIR/server" && npm install --legacy-peer-deps && npx tsc )
  echo "✓ Đã build: $BG_GEN"
else
  echo "✓ bgutil generator đã có: $BG_GEN"
fi

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
cp "$ROOT/$PLIST" "$DEST"

launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"
echo "✓ LaunchAgent đã nạp: $DEST"

echo "Đặt lịch đánh thức máy 06:55 hằng ngày (cần sudo)..."
sudo pmset repeat wakeorpoweron MTWRFSU 06:55:00

echo
echo "✓ Xong. Kiểm tra:"
echo "    launchctl list | grep podcastnotes"
echo "    pmset -g sched"
echo "Chạy thử ngay:  launchctl start com.podcastnotes.daily  (rồi xem logs/daily.log)"
