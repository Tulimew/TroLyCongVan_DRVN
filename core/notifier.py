import requests
import winsound
from core import db

def play_alert_chime():
    """Phát âm thanh chuông báo trên Windows"""
    if db.get_setting("enable_sound", "1") != "1":
        return
    try:
        # Phát âm thanh chuẩn Windows Asterisk hoặc tự tạo beep
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception as e:
        pass

def send_telegram_alert(text):
    """Gửi cảnh báo qua Telegram bot đã cấu hình"""
    token = db.get_setting("telegram_token", "")
    chat_id = db.get_setting("telegram_chat_id", "")
    enable = db.get_setting("enable_telegram", "1")

    if enable != "1" or not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10, allow_redirects=False)
        response.raise_for_status()
    except requests.RequestException:
        print("[Notifier] Không gửi được thông báo Telegram.")
