"""
Interactive Telegram Setup Wizard for GATE 2027 Companion
"""

import sys
import json
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

sys.path.insert(0, str(BASE_DIR / "scripts"))
from telegram_sender import send_telegram_message, get_latest_chat_id


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Configure Telegram Daily 7:00 PM Alerts")
    parser.add_argument("--token", help="Telegram Bot Token from @BotFather")
    parser.add_argument("--chat-id", help="Your Telegram User/Chat ID")
    parser.add_argument("--auto-chat-id", action="store_true", help="Auto-detect Chat ID from bot updates")
    parser.add_argument("--test", action="store_true", help="Send test message with current credentials")
    args = parser.parse_args()

    cfg = load_config()
    tg_cfg = cfg.setdefault("telegram", {"enabled": True, "bot_token": "", "chat_id": ""})

    print("=" * 65)
    print("  📱 GATE 2027 TELEGRAM AUTOMATION SETUP")
    print("=" * 65)

    token = args.token or tg_cfg.get("bot_token")
    chat_id = args.chat_id or tg_cfg.get("chat_id")

    if not token:
        print("\n  👉 QUICK 2-MINUTE TELEGRAM SETUP GUIDE:")
        print("  1. Open Telegram on your phone or desktop.")
        print("  2. Search for '@BotFather' and tap START.")
        print("  3. Send: /newbot")
        print("  4. Follow prompts to name your bot (e.g., 'My GATE 2027 Mentor').")
        print("  5. BotFather will give you a token like:")
        print("     '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ'")
        print("  6. Next, search for your new bot in Telegram and click START (/start).\n")
        
        # Interactive prompt if running in interactive terminal
        try:
            token = input("  Enter your Bot Token: ").strip()
        except EOFError:
            print("  ⚠️ Non-interactive terminal. Please run:")
            print("     python scripts/setup_telegram.py --token <YOUR_TOKEN> --chat-id <YOUR_CHAT_ID>")
            return

    if not token:
        print("  ❌ Error: Bot token cannot be empty.")
        return

    # Auto-detect chat_id if not provided
    if not chat_id or args.auto_chat_id:
        print(f"\n  🔍 Fetching your Chat ID from recent bot messages...")
        detected_id, info = get_latest_chat_id(token)
        if detected_id:
            chat_id = str(detected_id)
            print(f"  ✅ Found Telegram Chat: {info} (Chat ID: {chat_id})")
        else:
            print(f"  ℹ️ {info}")
            try:
                chat_id = input("  Enter your Telegram Chat ID manually (or from @userinfobot): ").strip()
            except EOFError:
                pass

    if not chat_id:
        print("  ⚠️ Chat ID missing. Please message your bot on Telegram (/start) and run:")
        print(f"     python scripts/setup_telegram.py --token {token} --auto-chat-id")
        return

    # Save to config.json
    tg_cfg["enabled"] = True
    tg_cfg["bot_token"] = token
    tg_cfg["chat_id"] = str(chat_id)
    save_config(cfg)
    print("\n  💾 Configuration saved successfully in config.json!")

    # Test transmission
    print("  🚀 Sending verification message to your Telegram...")
    test_msg = """🎉 <b>GATE 2027 Companion Connected!</b>
━━━━━━━━━━━━━━━━━━━━━
✅ Your Telegram is now linked to the <b>Daily 7:00 PM Automation</b>.

Every evening at <b>7:00 PM IST</b>, you will receive:
• Tonight's GATE syllabus topic
• High-yield formula takeaways
• Direct clickable YouTube classes & playlists
• Practice question targets

<i>Stay disciplined. Excellence is a habit. 🔥</i>
"""
    success, res = send_telegram_message(test_msg, token, chat_id)
    if success:
        print("  ✅ SUCCESS: Test message delivered to your Telegram! Check your phone. 📲")
    else:
        print(f"  ⚠️ Failed to deliver test message: {res}")


if __name__ == "__main__":
    main()
