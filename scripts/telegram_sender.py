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


import os

def get_telegram_credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return token or None, cid or None


def split_message(text, max_len=3900):
    if len(text) <= max_len:
        return [text]
    chunks = []
    current = ""
    for raw_line in text.split("\n"):
        # If an individual line exceeds max_len, hard-slice it
        while len(raw_line) > max_len:
            chunks.append(raw_line[:max_len])
            raw_line = raw_line[max_len:]

        if len(current) + len(raw_line) + 1 <= max_len:
            current += (raw_line + "\n")
        else:
            if current:
                chunks.append(current.strip())
            current = raw_line + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:max_len]]


def send_telegram_message(text, bot_token=None, chat_id=None, parse_mode="HTML", reply_markup=None):
    """
    Sends a message via Telegram Bot API with automatic message splitting for long texts.
    Returns (success: bool, response_dict_or_error_str)
    """
    token = bot_token
    cid = chat_id

    if not token or not cid:
        c_token, c_cid = get_telegram_credentials()
        token = token or c_token
        cid = cid or c_cid

    if not token or not cid:
        return False, "Missing bot_token or chat_id."

    chunks = split_message(text, max_len=3900)
    last_res = (True, {})
    ctx = ssl.create_default_context()

    for idx, chunk in enumerate(chunks):
        is_last = (idx == len(chunks) - 1)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": cid,
            "text": chunk,
            "disable_web_page_preview": False
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if is_last and reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                last_res = (res_data.get("ok", False), res_data)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            if parse_mode == "HTML" and "can't parse entities" in error_body.lower():
                import re
                clean_chunk = re.sub(r"<[^>]+>", "", chunk)
                payload["text"] = clean_chunk
                payload.pop("parse_mode", None)
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        last_res = (res_data.get("ok", False), res_data)
                except Exception:
                    pass
            else:
                return False, f"Telegram API HTTP Error {e.code}: {error_body}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    return last_res


def answer_callback_query(callback_query_id, bot_token=None, text=None, show_alert=False):
    """
    Acknowledges Telegram callback_query (stops loading spinner on buttons).
    """
    token = bot_token
    if not token:
        token, _ = get_telegram_credentials()
    if not token or not callback_query_id:
        return False

    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        ctx = ssl.create_default_context()
        urllib.request.urlopen(req, context=ctx, timeout=5)
        return True
    except Exception:
        return False


def send_telegram_poll(chat_id, question, options, correct_option_id, explanation, bot_token=None):
    """
    Sends a native Telegram Quiz Poll with instant green/red reveal and confetti.
    """
    token = bot_token
    if not token:
        token, _ = get_telegram_credentials()
    if not token:
        return False, "Token missing"

    url = f"https://api.telegram.org/bot{token}/sendPoll"
    expl = (explanation or "GATE 2027 Concept Revision")[:200]
    opts = [str(o)[:100] for o in options]

    payload = {
        "chat_id": chat_id,
        "question": question[:300],
        "options": opts,
        "is_anonymous": False,
        "type": "quiz",
        "correct_option_id": int(correct_option_id),
        "explanation": expl,
        "explanation_parse_mode": "HTML"
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            return res_data.get("ok", False), res_data
    except Exception as e:
        return False, f"Error sending poll: {e}"


def download_telegram_file(file_id, bot_token=None):
    """
    Retrieves the raw bytes of a file (e.g. photo) sent to Telegram.
    """
    token = bot_token
    if not token:
        token, _ = get_telegram_credentials()
    if not token or not file_id:
        return None

    url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                return None
            file_path = data.get("result", {}).get("file_path")
            if not file_path:
                return None

        dl_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        dl_req = urllib.request.Request(dl_url)
        with urllib.request.urlopen(dl_req, context=ctx, timeout=20) as dl_resp:
            return dl_resp.read()
    except Exception as e:
        print(f"Error downloading file {file_id}: {e}")
        return None


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
    subject_name = active_module.get("subject_name", "Core ECE Subject")
    weightage = active_module.get("subject_weightage", "")
    module_id = active_module.get("id", "")
    module_title = active_module.get("title", "")

    # Handle topics or key_concepts
    topics = active_module.get("key_concepts") or active_module.get("topics", [])
    topics_html = "\n".join([f"  ▫️ <i>{t}</i>" for t in topics])

    # Handle formulas or key_points
    formulas = active_module.get("formulas", [])
    if formulas:
        key_points = "\n".join([f"  • <code>{f}</code>" for f in formulas])
    else:
        key_points = f"<i>{active_module.get('key_points', 'Master the core formulas and standard derivations.')}</i>"

    # Practice target
    pyq_target = active_module.get("practice_pyqs") or active_module.get("pyq_target", "Practice 5 standard GATE PYQs")

    # Handle YouTube class
    yt = active_module.get("youtube_class", {})
    rec_videos = active_module.get("recommended_videos", [])
    videos_html = ""
    if yt and yt.get("url"):
        videos_html += f"  ▶️ <a href=\"{yt.get('url')}\"><b>{yt.get('title')} ({yt.get('educator', 'Educator')})</b></a>\n"
    for i, v in enumerate(rec_videos, 1):
        videos_html += f"  {i}. <a href=\"{v.get('url')}\"><b>{v.get('title')}</b></a>\n"

    featured_pl = active_module.get("featured_playlist", {})
    if featured_pl and featured_pl.get("playlist_url"):
        videos_html += f"  📁 <a href=\"{featured_pl.get('playlist_url')}\"><b>{featured_pl.get('name')} Full Playlist</b></a>\n"

    msg = f"""🎯 <b>GATE ECE 2027 STUDY MISSION (7:00 PM)</b>
━━━━━━━━━━━━━━━━━━━━━
⏳ <b>Countdown:</b> {days_left} Days Remaining (Feb 2027)
🔥 <b>Daily Streak:</b> {streak_days} Days
📊 <b>Progress:</b> {completed_count}/{total_count} Modules Completed

📚 <b>Active Subject:</b> <b>{subject_name}</b> {f'[{weightage}]' if weightage else ''}
📌 <b>Topic:</b> <code>[{module_id}]</code> <b>{module_title}</b>

📝 <b>Core Focus Concepts:</b>
{topics_html}

💡 <b>Essential Formulas & Relations:</b>
{key_points}

🎯 <b>Tonight's Goal:</b>
<b>{pyq_target}</b>

📺 <b>Recommended YouTube Lecture Class:</b>
{videos_html}
━━━━━━━━━━━━━━━━━━━━━
💬 <i>Ask me any doubt about this topic right here in chat!</i>
⚡ <i>Type <code>/complete</code> to mark done, or <code>/subject</code> to switch subjects.</i>
"""
    return msg
