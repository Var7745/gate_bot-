"""
GATE 2027 Daily 7:00 PM Automation & Study Dispatcher
----------------------------------------------------
Executes daily at 19:00 IST to:
1. Identify today's syllabus targets & milestones.
2. Recommend curated, high-yield YouTube lecture classes.
3. Fire native Windows desktop notifications with clickable actions.
4. Auto-launch recommended lecture in default browser.
5. Track streaks, module completion, and PYQ goals.
"""

import os
import sys
import json
import subprocess
import webbrowser
from datetime import datetime, date
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCRIPTS_DIR = BASE_DIR / "scripts"
CONFIG_FILE = BASE_DIR / "config.json"
TRACKER_FILE = DATA_DIR / "progress_tracker.json"

sys.path.insert(0, str(SCRIPTS_DIR))
from telegram_sender import send_telegram_message, format_gate_message


def load_json(filepath, default=None):
    if not os.path.exists(filepath):
        return default or {}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_current_target(config, syllabus, tracker):
    completed = set(tracker.get("completed_modules", []))
    
    # Iterate through all modules across subjects
    all_modules = []
    for subject in syllabus.get("subjects", []):
        for module in subject.get("modules", []):
            mod_copy = dict(module)
            mod_copy["subject_name"] = subject.get("name")
            mod_copy["subject_weightage"] = subject.get("weightage")
            mod_copy["featured_playlist"] = subject.get("featured_playlist")
            mod_copy["is_completed"] = module.get("id") in completed
            all_modules.append(mod_copy)

    # First incomplete module
    active_module = None
    for m in all_modules:
        if not m["is_completed"]:
            active_module = m
            break

    if not active_module and all_modules:
        active_module = all_modules[-1]  # All completed, point to final revision

    return active_module, all_modules


def calculate_countdown(target_date_str):
    try:
        target_date = datetime.fromisoformat(target_date_str.replace("Z", ""))
        now = datetime.now()
        diff = target_date - now
        days = diff.days
        hours = diff.seconds // 3600
        return max(0, days), hours
    except Exception:
        return 155, 0


def trigger_windows_notification(title, message, subtext, url):
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
    except Exception as e:
        print(f"[Warning] Failed to show Windows toast notification: {e}")
        return False


def run_dispatch(args):
    config = load_json(CONFIG_FILE)
    branch = config.get("branch", "CS").lower()
    syllabus_file = DATA_DIR / f"syllabus_{branch}.json"

    if not syllabus_file.exists():
        syllabus_file = DATA_DIR / "syllabus_cs.json"

    syllabus = load_json(syllabus_file)
    tracker = load_json(TRACKER_FILE, default={
        "completed_modules": [],
        "current_streak_days": 0,
        "daily_logs": []
    })

    active_module, all_modules = get_current_target(config, syllabus, tracker)
    days_left, _ = calculate_countdown(config.get("exam_target_date", "2027-02-06"))

    total_modules = len(all_modules)
    completed_count = sum(1 for m in all_modules if m["is_completed"])
    progress_pct = (completed_count / total_modules * 100) if total_modules > 0 else 0

    # Pick recommended video
    rec_videos = active_module.get("recommended_videos", [])
    primary_video = rec_videos[0] if rec_videos else {
        "title": active_module.get("title"),
        "url": active_module.get("featured_playlist", {}).get("url", "https://youtube.com")
    }

    # Formatting CLI Output
    sep = "=" * 70
    print("\n" + sep)
    print(f"  🔔 GATE 2027 EVENING 7:00 PM STUDY DISPATCH")
    print(sep)
    print(f"  📅 Date: {datetime.now().strftime('%A, %d %B %Y')} | ⏰ Time: {datetime.now().strftime('%I:%M %p')}")
    print(f"  🎯 Target: {config.get('exam_name')} | ⏳ Countdown: {days_left} Days Remaining")
    print(f"  📈 Syllabus Progress: {completed_count}/{total_modules} Modules ({progress_pct:.1f}%) | 🔥 Streak: {tracker.get('current_streak_days', 0)} Days")
    print(sep)
    print(f"  📚 SUBJECT: {active_module.get('subject_name')} [Weightage: {active_module.get('subject_weightage')}]")
    print(f"  📌 TODAY'S TOPIC: [{active_module.get('id')}] {active_module.get('title')}")
    print(f"  📝 Subtopics:")
    for t in active_module.get("topics", []):
        print(f"     • {t}")
    print(f"\n  💡 Key Takeaway: {active_module.get('key_points')}")
    print(f"  🎯 Tonight's Target: {active_module.get('pyq_target')}")
    print(sep)
    print(f"  📺 RECOMMENDED YOUTUBE VIDEO CLASS:")
    print(f"     🎬 Title: {primary_video.get('title')}")
    print(f"     🔗 URL  : {primary_video.get('url')}")
    if len(rec_videos) > 1:
        print(f"  📺 ALTERNATIVE LECTURE:")
        print(f"     🎬 Title: {rec_videos[1].get('title')}")
        print(f"     🔗 URL  : {rec_videos[1].get('url')}")
    print(sep)

    # Optional Action: Complete module
    if "--complete" in args:
        target_id = active_module.get("id")
        comp_idx = args.index("--complete")
        if comp_idx + 1 < len(args) and not args[comp_idx + 1].startswith("--"):
            target_id = args[comp_idx + 1]

        if target_id not in tracker.get("completed_modules", []):
            tracker.setdefault("completed_modules", []).append(target_id)
            tracker["current_streak_days"] = tracker.get("current_streak_days", 0) + 1
            tracker["last_active_date"] = date.today().isoformat()
            save_json(TRACKER_FILE, tracker)
            print(f"  ✅ SUCCESS: Module [{target_id}] marked as completed! Streak is now {tracker['current_streak_days']} days! 🎉\n")
        else:
            print(f"  ℹ️ Module [{target_id}] was already completed.\n")
        return

    # Notification & Auto-open logic
    should_notify = "--notify" in args or config.get("notification_enabled", True)
    should_open = "--open" in args or ("--no-open" not in args and config.get("auto_open_youtube", True) and "--test" not in args)

    if should_notify:
        notif_title = f"🎯 GATE 2027: {active_module.get('title')}"
        notif_msg = f"{active_module.get('subject_name')} | Streak: {tracker.get('current_streak_days', 0)}d 🔥"
        notif_subtext = f"Class: {primary_video.get('title')[:45]}..."
        print("  📢 Triggering native Windows notification banner...")
        trigger_windows_notification(notif_title, notif_msg, notif_subtext, primary_video.get("url"))

    if should_open:
        print(f"  🚀 Launching YouTube class in your default web browser...")
        webbrowser.open(primary_video.get("url"))

    if "--dashboard" in args:
        dash_path = BASE_DIR / "dashboard" / "index.html"
        if dash_path.exists():
            print("  📊 Opening Interactive Study Dashboard...")
            webbrowser.open(dash_path.as_uri())

    # Telegram Dispatch
    tg_cfg = config.get("telegram", {})
    tg_enabled = tg_cfg.get("enabled", True)
    tg_token = tg_cfg.get("bot_token", "").strip()
    tg_chat_id = str(tg_cfg.get("chat_id", "")).strip()

    if tg_enabled and tg_token and tg_chat_id:
        print("  📱 Dispatching tonight's mission directly to your Telegram...")
        tg_text = format_gate_message(
            active_module,
            days_left,
            tracker.get("current_streak_days", 0),
            completed_count,
            total_modules
        )
        ok, res = send_telegram_message(tg_text, tg_token, tg_chat_id)
        if ok:
            print("  ✅ Telegram alert delivered to your phone! 📲")
        else:
            print(f"  ⚠️ Telegram alert notice: {res}")
    elif tg_enabled and ("--telegram" in args or "--test" not in args):
        print("  📱 Telegram alert: Bot token or chat ID not yet configured.")
        print("     To link your Telegram account, run: python scripts/setup_telegram.py")

    # Log dispatch
    today_str = date.today().isoformat()
    daily_logs = tracker.get("daily_logs", [])
    if not any(log.get("date") == today_str for log in daily_logs):
        daily_logs.append({
            "date": today_str,
            "time": "19:00",
            "module_id": active_module.get("id"),
            "subject": active_module.get("subject_name"),
            "title": active_module.get("title"),
            "status": "dispatched"
        })
        tracker["daily_logs"] = daily_logs
        save_json(TRACKER_FILE, tracker)

    print("  ✨ Have an impactful study session tonight! To mark today's module done:")
    print(f"     python scripts/daily_dispatch.py --complete {active_module.get('id')}\n")


if __name__ == "__main__":
    run_dispatch(sys.argv[1:])
