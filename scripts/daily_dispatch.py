"""
GATE 2027 Daily 7:00 PM Automation & Study Dispatcher
Uses unified study_engine for syllabus navigation and dispatches.
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
SCRIPTS_DIR = BASE_DIR / "scripts"
CONFIG_FILE = BASE_DIR / "config.json"
TRACKER_FILE = DATA_DIR / "progress_tracker.json"

sys.path.insert(0, str(SCRIPTS_DIR))
from study_engine import (
    get_current_target,
    calculate_countdown,
    get_syllabus,
    load_json
)
from telegram_sender import send_telegram_message, format_gate_message


def show_windows_toast(title, message, subtext="", url="https://youtube.com"):
    ps_script = SCRIPTS_DIR / "trigger_notification.ps1"
    if not ps_script.exists():
        return False
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(ps_script),
        "-Title", title,
        "-Message", message,
        "-Subtext", subtext,
        "-Url", url
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return True
    except Exception:
        return False


def run_dispatch(args=None):
    config = load_json(CONFIG_FILE)
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE, default={"completed_modules": [], "current_streak_days": 0})

    active_module, all_modules = get_current_target(config, syllabus, tracker)
    days_left, _ = calculate_countdown(config.get("exam_target_date", "2027-02-06"))

    total_modules = len(all_modules)
    completed_count = sum(1 for m in all_modules if m.get("is_completed"))
    progress_pct = (completed_count / total_modules * 100) if total_modules > 0 else 0

    yt = active_module.get("youtube_class", {})
    yt_url = yt.get("url", "https://youtube.com")

    print("=" * 65)
    print("  🔔 GATE 2027 EVENING 7:00 PM STUDY DISPATCH")
    print("=" * 65)
    print(f"  🎯 Target: GATE 2027 ECE | ⏳ Countdown: {days_left} Days Remaining")
    print(f"  📈 Syllabus Progress: {completed_count}/{total_modules} Modules ({progress_pct:.1f}%) | 🔥 Streak: {tracker.get('current_streak_days', 1)} Days")
    print(f"  📚 SUBJECT: {active_module.get('subject_name')} [{active_module.get('subject_code')}]")
    print(f"  📌 TOPIC: [{active_module.get('id')}] {active_module.get('title')}")
    print(f"  📺 RECOMMENDED VIDEO: {yt.get('title', 'Lecture Class')} ({yt.get('educator', 'Faculty')})")
    print("=" * 65)

    # Windows Toast
    show_windows_toast(
        title="🔔 GATE 2027 Study Mission",
        message=f"[{active_module.get('id')}] {active_module.get('title')}",
        subtext=f"{active_module.get('subject_name')} | {days_left} Days Left",
        url=yt_url
    )

    # Telegram Message
    tg_cfg = config.get("telegram", {})
    if tg_cfg.get("enabled", True):
        token = os.environ.get("TELEGRAM_BOT_TOKEN") or tg_cfg.get("bot_token")
        cid = os.environ.get("TELEGRAM_CHAT_ID") or tg_cfg.get("chat_id")
        if token and cid:
            msg = format_gate_message(
                active_module,
                days_left,
                tracker.get("current_streak_days", 1),
                completed_count,
                total_modules
            )
            actions = {
                "inline_keyboard": [
                    [{"text": "▶️ Watch Lecture on YouTube", "url": yt_url}],
                    [{"text": "📝 Practice Quiz", "callback_data": "act_pyq"}]
                ]
            }
            send_telegram_message(msg, token, cid, reply_markup=actions)
            print("Telegram study alert dispatched successfully!")


if __name__ == "__main__":
    run_dispatch()