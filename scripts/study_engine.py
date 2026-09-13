"""
Unified Study Engine for GATE 2027 ECE Companion
Single source of truth for:
- Syllabus navigation & active module selection
- Exam countdown calculations with IST timezone awareness
- Streak tracking with Indian calendar dates
- Dispatch message formatting
"""

import os
import json
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

# IST Timezone UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
CONFIG_FILE = BASE_DIR / "config.json"
TRACKER_FILE = DATA_DIR / "progress_tracker.json"
SYLLABUS_FILE = DATA_DIR / "syllabus_ec.json"


def load_json(filepath, default=None):
    if not os.path.exists(filepath):
        return default or {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default or {}


def save_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save {filepath}: {e}")


def get_syllabus():
    """Returns the canonical GATE ECE syllabus."""
    if not SYLLABUS_FILE.exists():
        return {"subjects": []}
    try:
        with open(SYLLABUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"subjects": []}


def calculate_countdown(target_date_str="2027-02-06T09:30:00"):
    try:
        target = datetime.fromisoformat(target_date_str.replace("Z", "")).replace(tzinfo=IST)
        now = datetime.now(IST)
        delta = target - now
        days = max(0, delta.days)
        hours = max(0, delta.seconds // 3600)
        return days, hours
    except Exception:
        return 145, 0


def get_current_target(config=None, syllabus=None, tracker=None):
    """
    Calculates the active module dynamically:
    Checks active_subject_code, finds the next unfinished module in that subject.
    Never relies on stale active_module_id!
    """
    config = config or load_json(CONFIG_FILE)
    syllabus = syllabus or get_syllabus()
    tracker = tracker or load_json(TRACKER_FILE)

    completed = set(tracker.get("completed_modules", []))
    active_subj_code = config.get("active_subject_code", "NET").upper().strip()

    all_modules = []
    subject_modules = []

    for subject in syllabus.get("subjects", []):
        s_code = subject.get("id", "").upper().strip()
        is_selected = (s_code == active_subj_code)

        for mod in subject.get("modules", []):
            m_copy = dict(mod)
            m_copy["subject_name"] = subject.get("name")
            m_copy["subject_code"] = s_code
            m_copy["subject_weightage"] = subject.get("weightage", "8-10%")
            m_copy["is_completed"] = m_copy.get("id") in completed
            all_modules.append(m_copy)
            if is_selected:
                subject_modules.append(m_copy)

    # 1. Look for first incomplete module in active subject
    for mod in subject_modules:
        if not mod["is_completed"]:
            return mod, all_modules

    # 2. If all in active subject completed, return last in active subject
    if subject_modules:
        return subject_modules[-1], all_modules

    # 3. Fallback to first available module
    if all_modules:
        return all_modules[0], all_modules

    return {"id": "NET-M01", "title": "Network Theorems", "key_concepts": [], "formulas": []}, all_modules


def update_streak_on_complete(mid):
    """
    Records a completed module using IST calendar date-aware streak calculation.
    """
    tracker = load_json(TRACKER_FILE)
    today = datetime.now(IST).date()
    last_active_str = tracker.get("last_active_date")

    if last_active_str:
        try:
            last_date = date.fromisoformat(last_active_str)
            delta = (today - last_date).days
            if delta == 1:
                tracker["current_streak_days"] = tracker.get("current_streak_days", 0) + 1
            elif delta == 0:
                pass  # Same day activity, maintain streak
            else:
                tracker["current_streak_days"] = 1  # Reset streak after break
        except Exception:
            tracker["current_streak_days"] = 1
    else:
        tracker["current_streak_days"] = 1

    tracker["last_active_date"] = today.isoformat()

    completed_list = tracker.setdefault("completed_modules", [])
    already_done = mid in completed_list
    if not already_done:
        completed_list.append(mid)

    save_json(TRACKER_FILE, tracker)
    return tracker, not already_done