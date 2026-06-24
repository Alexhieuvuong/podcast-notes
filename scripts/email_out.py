"""
Gửi note qua Resend — chép gọn từ ~/ai-daily-digest/scripts/email_brief.py.
No-op nếu thiếu RESEND_API_KEY.

Env: RESEND_API_KEY (bắt buộc để gửi), EMAIL_TO (mặc định hieudinhvuong@gmail.com —
Resend test mode chỉ gửi tới chủ tài khoản), EMAIL_FROM (mặc định onboarding@resend.dev).
"""

import os

import requests
import markdown as md_lib

DEFAULT_TO = "hieudinhvuong@gmail.com"
DEFAULT_FROM = "onboarding@resend.dev"


def _wrap_html(inner):
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f6f8fa;">
  <div style="max-width:680px;margin:0 auto;padding:24px 20px;
              font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
              color:#1f2328;line-height:1.6;font-size:15px;">{inner}</div>
</body></html>"""


def send_email(subject, markdown_body):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("[email] RESEND_API_KEY chưa đặt — bỏ qua gửi email.")
        return False
    to_addr = os.environ.get("EMAIL_TO", DEFAULT_TO)
    from_addr = os.environ.get("EMAIL_FROM", DEFAULT_FROM)
    html = _wrap_html(md_lib.markdown(markdown_body, extensions=["extra"]))
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_addr, "to": [to_addr], "subject": subject, "html": html},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            print(f"[email] Đã gửi tới {to_addr} (id: {resp.json().get('id')})")
            return True
        print(f"[email] Gửi thất bại {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[email] Lỗi khi gửi: {e}")
    return False
