"""
GATE 2027 Interactive AI Telegram Bot & 24/7 Service Daemon
------------------------------------------------------------
Features:
1. Interactive Real-Time AI Chat on Telegram (@Varshith772bot)
2. Command Handlers: /start, /today, /pyq, /status, /complete, /setkey, /help
3. Background 7:00 PM Automated Daily Dispatcher
4. Runs locally or deployed 24/7 on free cloud hosting (Render/Koyeb)
"""

import os
import sys
import json
import time
import ssl
import threading
import urllib.request
import urllib.parse
import http.server
import socketserver
from datetime import datetime, date
from pathlib import Path

# Ensure UTF-8 output and instant line buffering on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
SCRIPTS_DIR = BASE_DIR / "scripts"
TRACKER_FILE = DATA_DIR / "progress_tracker.json"

sys.path.insert(0, str(SCRIPTS_DIR))
from ai_engine import generate_gate_ai_reply, generate_pyq_question, save_config, load_config
from telegram_sender import send_telegram_message, format_gate_message
from daily_dispatch import get_current_target, calculate_countdown, load_json, save_json


def send_chat_action(bot_token, chat_id, action="typing"):
    """Shows 'typing...' status in Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
    payload = {"chat_id": chat_id, "action": action}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        ctx = ssl.create_default_context()
        urllib.request.urlopen(req, context=ctx, timeout=5)
    except Exception:
        pass


def handle_command_start(chat_id, user_name, bot_token):
    msg = f"""👋 <b>Hello {user_name}! Welcome to your GATE 2027 AI Command Center.</b>
━━━━━━━━━━━━━━━━━━━━━
I am your personal AI Study Mentor & Automation Companion for <b>GATE 2027</b>.

🎯 <b>What I do for you:</b>
• <b>Everyday at 7:00 PM:</b> I dispatch tonight's syllabus topic, key formulas & recommended YouTube video classes.
• <b>Ask me any doubt:</b> Send any question (e.g. <i>"Explain Paging in OS"</i> or <i>"Dijkstra vs Bellman Ford"</i>).
• <b>Practice PYQs:</b> Type <code>/pyq</code> to get a practice question.

⚡ <b>Available Commands:</b>
• <code>/today</code> - Tonight's 7:00 PM lecture class & targets
• <code>/pyq</code> - Practice a GATE question on today's module
• <code>/status</code> - Syllabus progress & countdown
• <code>/complete</code> - Mark today's module complete (+1 streak 🔥)
• <code>/setkey &lt;KEY&gt;</code> - Connect your free Gemini API key
• <code>/help</code> - Command reference
"""
    send_telegram_message(msg, bot_token, chat_id)


def handle_command_today(chat_id, bot_token):
    config = load_config()
    syllabus = load_json(DATA_DIR / "syllabus_cs.json")
    tracker = load_json(TRACKER_FILE)
    active_module, all_modules = get_current_target(config, syllabus, tracker)
    days_left, _ = calculate_countdown(config.get("exam_target_date", "2027-02-06"))

    completed_count = sum(1 for m in all_modules if m["is_completed"])
    total_count = len(all_modules)

    msg = format_gate_message(
        active_module,
        days_left,
        tracker.get("current_streak_days", 1),
        completed_count,
        total_count
    )
    send_telegram_message(msg, bot_token, chat_id)


def handle_command_status(chat_id, bot_token):
    config = load_config()
    syllabus = load_json(DATA_DIR / "syllabus_cs.json")
    tracker = load_json(TRACKER_FILE)
    active_module, all_modules = get_current_target(config, syllabus, tracker)
    days_left, _ = calculate_countdown(config.get("exam_target_date", "2027-02-06"))

    total_modules = len(all_modules)
    completed_count = sum(1 for m in all_modules if m["is_completed"])
    pct = (completed_count / total_modules * 100) if total_modules > 0 else 0

    msg = f"""📊 <b>GATE 2027 Preparation Status</b>
━━━━━━━━━━━━━━━━━━━━━
⏳ <b>Countdown:</b> {days_left} Days Remaining (Feb 2027)
🔥 <b>Study Streak:</b> {tracker.get('current_streak_days', 1)} Days
📈 <b>Syllabus Completed:</b> {completed_count}/{total_modules} Modules ({pct:.1f}%)

📌 <b>Current Focus Module:</b>
[<code>{active_module.get('id')}</code>] <b>{active_module.get('title')}</b>
Subject: <i>{active_module.get('subject_name')}</i>

🎯 <i>Type <code>/today</code> to view tonight's lecture class or <code>/pyq</code> to practice!</i>
"""
    send_telegram_message(msg, bot_token, chat_id)


def handle_command_complete(chat_id, bot_token):
    config = load_config()
    syllabus = load_json(DATA_DIR / "syllabus_cs.json")
    tracker = load_json(TRACKER_FILE)
    active_module, _ = get_current_target(config, syllabus, tracker)

    mid = active_module.get("id")
    if mid and mid not in tracker.get("completed_modules", []):
        tracker.setdefault("completed_modules", []).append(mid)
        tracker["current_streak_days"] = tracker.get("current_streak_days", 0) + 1
        tracker["last_active_date"] = date.today().isoformat()
        save_json(TRACKER_FILE, tracker)
        msg = f"""🎉 <b>Module Completed!</b>
━━━━━━━━━━━━━━━━━━━━━
Awesome job! Module <code>[{mid}] {active_module.get('title')}</code> has been marked completed.

🔥 <b>Streak Increased:</b> <b>{tracker['current_streak_days']} Days!</b>
Keep up the momentum. See you tomorrow evening at 7:00 PM! 🚀
"""
    else:
        msg = f"ℹ️ Module <code>[{mid}]</code> is already marked as completed. Use <code>/status</code> to check progress."

    send_telegram_message(msg, bot_token, chat_id)


def handle_command_setkey(chat_id, text, bot_token):
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        msg = """⚠️ <b>How to set your Free Google Gemini API Key:</b>
━━━━━━━━━━━━━━━━━━━━━
1. Get a free API key at: <b>https://aistudio.google.com/app/apikey</b>
2. Send: <code>/setkey YOUR_API_KEY_HERE</code>
"""
        send_telegram_message(msg, bot_token, chat_id)
        return

    key = parts[1].strip()
    config = load_config()
    config.setdefault("ai_engine", {})["gemini_api_key"] = key
    config["ai_engine"]["provider"] = "gemini"
    save_config(config)

    msg = """✅ <b>Google Gemini Free Cloud AI Connected!</b>
━━━━━━━━━━━━━━━━━━━━━
Your Gemini API Key has been saved. Full conversational AI is now unlocked!

Try asking me any question, for example:
• <i>"Explain Amortized Analysis with an example"</i>
• <i>"Give me a shortcut to find candidate keys in DBMS"</i>
• <i>"How to solve 2-mark NAT questions on Cache memory?"</i>
"""
    send_telegram_message(msg, bot_token, chat_id)


def handle_message(update, bot_token):
    msg_obj = update.get("message", {})
    chat_id = msg_obj.get("chat", {}).get("id")
    text = (msg_obj.get("text") or "").strip()
    user_name = msg_obj.get("from", {}).get("first_name", "Student")

    if not chat_id or not text:
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Message from {user_name} ({chat_id}): {text}")

    cmd = text.lower().strip()

    # Flexible command routing (accepts with or without slash, case-insensitive)
    if cmd in ("/start", "start"):
        handle_command_start(chat_id, user_name, bot_token)
    elif cmd in ("/today", "today"):
        handle_command_today(chat_id, bot_token)
    elif cmd in ("/status", "status"):
        handle_command_status(chat_id, bot_token)
    elif cmd in ("/complete", "complete", "done"):
        handle_command_complete(chat_id, bot_token)
    elif cmd in ("/pyq", "pyq"):
        send_chat_action(bot_token, chat_id, "typing")
        pyq_resp = generate_pyq_question()
        send_telegram_message(pyq_resp, bot_token, chat_id)
    elif cmd.startswith("/setkey") or cmd.startswith("setkey"):
        handle_command_setkey(chat_id, text, bot_token)
    elif cmd in ("/help", "help"):
        handle_command_start(chat_id, user_name, bot_token)
    else:
        # Standard question/doubt - route to AI
        send_chat_action(bot_token, chat_id, "typing")
        ai_reply = generate_gate_ai_reply(text)
        send_telegram_message(ai_reply, bot_token, chat_id)


def daily_scheduler_thread(bot_token, target_chat_id):
    """
    Background worker that triggers the daily 7:00 PM (19:00 IST) dispatch.
    """
    print("⏰ Background 7:00 PM Daily Scheduler active.")
    last_dispatched_day = None

    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # Check if time is 19:00 (7:00 PM) and not already dispatched today
            if now.hour == 19 and now.minute == 0 and last_dispatched_day != today_str:
                print(f"\n🔔 [7:00 PM] Triggering automated daily study dispatch to Telegram...")
                handle_command_today(target_chat_id, bot_token)
                last_dispatched_day = today_str

            time.sleep(30)
        except Exception as e:
            print(f"Error in daily scheduler: {e}")
            time.sleep(30)


class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = """<!DOCTYPE html>
<html>
<head><title>GATE 2027 Bot Online</title></head>
<body style="font-family: sans-serif; background: #0b0f19; color: #fff; padding: 40px; text-align: center;">
    <h1 style="color: #38bdf8;">🎯 GATE 2027 Telegram AI Bot</h1>
    <p style="color: #10b981; font-size: 20px; font-weight: bold;">● Status: 24/7 Cloud Service Online</p>
    <p>Bot: <b>@Varshith772bot</b></p>
    <p>User: <b>Varshith Goud</b></p>
    <p style="color: #94a3b8; font-size: 13px;">Daily 7:00 PM Automation & AI Chat Active</p>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", port), HealthHandler) as httpd:
            print(f"🌐 Cloud HTTP Health Service active on port {port} (Ready for Render/Koyeb)")
            httpd.serve_forever()
    except Exception as e:
        print(f"Health server note: {e}")


def run_bot():
    config = load_config()
    tg_cfg = config.get("telegram", {})
    bot_token = tg_cfg.get("bot_token")
    target_chat_id = tg_cfg.get("chat_id")

    if not bot_token:
        print("❌ Error: Telegram bot_token missing from config.json. Run scripts/setup_telegram.py")
        sys.exit(1)

    print("=" * 65)
    print("  🚀 GATE 2027 TELEGRAM AI BOT SERVICE STARTED")
    print(f"  🤖 Bot Username: @{tg_cfg.get('bot_username', 'Varshith772bot')}")
    print(f"  👤 Linked User : {tg_cfg.get('user_name', 'Varshith Goud')} ({target_chat_id})")
    print("  ⚡ Listening for incoming messages & doubts...")
    print("=" * 65)

    # Start HTTP Health Server for Cloud Hosting (Render / Koyeb)
    t_http = threading.Thread(target=start_health_server, daemon=True)
    t_http.start()

    # Start daily scheduler thread
    if target_chat_id:
        t = threading.Thread(target=daily_scheduler_thread, args=(bot_token, target_chat_id), daemon=True)
        t.start()

    offset = 0
    ctx = ssl.create_default_context()

    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=20"
            req = urllib.request.Request(url, headers={"User-Agent": "GATE2027Bot/1.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        handle_message(update, bot_token)
        except urllib.error.URLError:
            time.sleep(3)
        except Exception as e:
            print(f"Polling loop notice: {e}")
            time.sleep(3)


if __name__ == "__main__":
    run_bot()
