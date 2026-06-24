#!/bin/bash
# Lập lịch chạy podcast-notes hằng ngày trên Mac:
#   - launchd (LaunchAgent) chạy job lúc 07:00
#   - pmset đánh thức máy lúc 06:55 (cần sudo; chỉ thức từ SLEEP, không từ tắt nguồn; nên cắm điện)
set -e

ROOT="$HOME/podcast-notes"
PLIST="com.podcastnotes.daily.plist"
DEST="$HOME/Library/LaunchAgents/$PLIST"

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
