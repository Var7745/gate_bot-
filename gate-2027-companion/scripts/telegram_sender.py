"""
Telegram Notification Dispatcher for GATE 2027 Study Companion
Uses standard Python urllib (no external dependencies required).
"""

import json
import urllib.request
import urllib.parse
import ssl
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"


def get_telegram_credentials():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            tg = cfg.get("telegram", {})
            return tg.get("bot_token", "").strip(), str(tg.get("chat_id", "")).strip()
    except Exception:
        return None, None


def send_telegram_message(text, bot_token=None, chat_id=None, parse_mode="HTML"):
    """
    Sends a message via Telegram Bot API.
    Returns (success: bool, response_dict_or_error_str)
    """
    token = bot_token
    cid = chat_id

    if not token or not cid:
        c_token, c_cid = get_telegram_credentials()
        token = token or c_token
        cid = cid or c_cid

    if not token or not cid:
        return False, "Missing bot_token or chat_id. Run python scripts/setup_telegram.py to configure."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            return res_data.get("ok", False), res_data
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return False, f"Telegram API HTTP Error {e.code}: {error_body}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


def get_latest_chat_id(bot_token):
    """
    Polls getUpdates to find the chat_id from recent messages sent to the bot.
    Helpful for automatic setup.
    """
    if not bot_token:
        return None, "Bot token required."

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GATE2027Bot/1.0"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if not res_data.get("ok"):
                return None, "Bot token invalid or Telegram API error."
            
            results = res_data.get("result", [])
            if not results:
                return None, "No messages received yet. Please open your bot in Telegram and click /start."
            
            # Get latest message
            last_msg = results[-1]
            chat = last_msg.get("message", {}).get("chat") or last_msg.get("my_chat_member", {}).get("chat")
            if chat:
                return chat.get("id"), chat.get("first_name", "User")
            return None, "Could not determine chat_id from updates."
    except Exception as e:
        return None, f"Error reaching Telegram: {str(e)}"


def format_gate_message(active_module, days_left, streak_days, completed_count, total_count):
    """
    Constructs a rich HTML message formatted specifically for Telegram mobile & desktop.
    """
    subject_name = active_module.get("subject_name", "Core Subject")
    weightage = active_module.get("subject_weightage", "")
    module_id = active_module.get("id", "")
    module_title = active_module.get("title", "")
    topics = active_module.get("topics", [])
    key_points = active_module.get("key_points", "")
    pyq_target = active_module.get("pyq_target", "")
    rec_videos = active_module.get("recommended_videos", [])
    featured_pl = active_module.get("featured_playlist", {})

    topics_html = "\n".join([f"  ▫️ <i>{t}</i>" for t in topics])
    
    videos_html = ""
    for i, v in enumerate(rec_videos, 1):
        v_title = v.get("title", "Lecture Class")
        v_url = v.get("url", "https://youtube.com")
        videos_html += f"  {i}. <a href=\"{v_url}\"><b>{v_title}</b></a>\n"

    if featured_pl and featured_pl.get("url"):
        videos_html += f"  📁 <a href=\"{featured_pl.get('url')}\"><b>Full Subject Playlist ({featured_pl.get('title', 'All Lectures')})</b></a>\n"

    msg = f"""🎯 <b>GATE 2027 EVENING 7:00 PM MISSION</b>
━━━━━━━━━━━━━━━━━━━━━
⏳ <b>Countdown:</b> {days_left} Days Remaining (Feb 2027)
🔥 <b>Daily Streak:</b> {streak_days} Days
📊 <b>Progress:</b> {completed_count}/{total_count} Modules Completed

📚 <b>Subject:</b> <b>{subject_name}</b> {f'[{weightage}]' if weightage else ''}
📌 <b>Topic:</b> <code>[{module_id}]</code> <b>{module_title}</b>

📝 <b>Today's Subtopics:</b>
{topics_html}

💡 <b>Key Formula & Takeaway:</b>
<i>{key_points}</i>

🎯 <b>Tonight's Practice Goal:</b>
<b>{pyq_target}</b>

📺 <b>Curated YouTube Video Classes:</b>
{videos_html}
━━━━━━━━━━━━━━━━━━━━━
✅ <i>Mark complete tonight via command:</i>
<code>python scripts/daily_dispatch.py --complete {module_id}</code>
"""
    return msg
