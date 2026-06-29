# podcast-notes

Chuyển podcast YouTube thành ghi chú tổng hợp tiếng Việt — tự động mỗi ngày.

## Tính năng

- Lấy transcript từ video YouTube (vượt rào phụ đề 2025 với PO token + cookie)
- Tổng hợp nội dung bằng Claude hoặc DeepSeek
- Lưu ghi chú dạng Markdown vào `notes/`
- Chạy tự động lúc 7:00 sáng qua launchd (macOS)

## Cài đặt

**Yêu cầu:** Python 3.10+, Node.js 18+, yt-dlp

```bash
git clone https://github.com/Alexhieuvuong/podcast-notes.git ~/podcast-notes
cd ~/podcast-notes
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Tạo file `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...   # nếu dùng Claude
API_KEY=sk-...                 # nếu dùng DeepSeek
NOTES_ENGINE=claude            # hoặc deepseek
YT_COOKIES_BROWSER=chrome      # trình duyệt để lấy cookie YouTube
```

Build bgutil PO-token generator (bắt buộc để lấy phụ đề YouTube):

```bash
git clone --branch 1.1.0 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git ~/bgutil-ytdlp-pot-provider
cd ~/bgutil-ytdlp-pot-provider/server && npm install --legacy-peer-deps && npx tsc
```

## Dùng thủ công

```bash
python scripts/main.py https://www.youtube.com/watch?v=VIDEO_ID
```

Ghi chú được lưu tại `notes/YYYY-MM-DD-ten-video.md`.

## Chạy tự động (macOS)

```bash
bash scripts/install_schedule.sh
```

Cài LaunchAgent chạy lúc 07:00 và đánh thức máy lúc 06:55. Xem log tại `logs/daily.log`.

## Kênh theo dõi

Chỉnh `feeds.txt` — mỗi dòng một kênh YouTube (`@handle`, channel ID, hoặc URL).

## License

[MIT](LICENSE)
