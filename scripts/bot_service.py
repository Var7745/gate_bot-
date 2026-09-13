"""
GATE 2027 Interactive AI Telegram Bot & 24/7 Service Daemon (v3.1 Production)
----------------------------------------------------------------------------
Features:
1. Interactive Real-Time AI Chat on Telegram with persistent multi-turn memory
2. Strict environment-only credentials & fail-closed authorization
3. Curated Authentic Historical GATE ECE PYQs vs AI-generated practice problems
4. Deterministic practice question evaluation via SQLite (practice_questions table)
5. Deduplicated quiz and PYQ tracking with topic-level analytics
6. Retry-safe 7:00 PM IST Automated Daily Dispatcher (verifies delivery)
7. Mathematical edge-case validation for /calc
8. Cloud HTTP Health Server for Render / Koyeb (Port 8080)
"""

import os
import sys
import json
import time
import math
import ssl
import threading
import urllib.request
import urllib.parse
import http.server
import socketserver
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

# IST timezone (UTC+5:30) for rock-solid scheduling across cloud hosts
IST = timezone(timedelta(hours=5, minutes=30))

# Ensure UTF-8 output and instant line buffering on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
    except Exception:
        pass

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
    load_json,
    save_json,
    update_streak_on_complete
)
from curated_pyq_bank import get_curated_pyq, CURATED_PYQ_BANK
from ai_engine import (
    generate_gate_ai_reply,
    generate_gate_ai_vision_reply,
    generate_practice_question,
    generate_native_quiz_poll,
    save_config,
    load_config
)
from telegram_sender import (
    send_telegram_message,
    send_telegram_poll,
    download_telegram_file,
    format_gate_message,
    answer_callback_query
)
from db_manager import (
    save_active_poll,
    get_active_poll,
    record_poll_attempt,
    save_practice_question,
    get_practice_question,
    record_practice_attempt,
    record_pyq_attempt,
    get_analytics_summary,
    get_last_dispatch_date,
    set_last_dispatch_date,
    clear_chat_history,
    get_latest_question
)

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🎯 Today's Mission"}, {"text": "📚 Switch Subject"}],
        [{"text": "📝 Practice Quiz"}, {"text": "🏛️ GATE PYQ"}],
        [{"text": "💡 Formula Sheet"}, {"text": "📈 Score & Stats"}],
        [{"text": "📺 YouTube Class"}, {"text": "✅ Mark Done"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

SUBJECT_INLINE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🌐 Networks & Signals (16M)", "callback_data": "sub_NET"},
            {"text": "🔬 Devices EDC (10M)", "callback_data": "sub_EDC"}
        ],
        [
            {"text": "⚡ Analog Circuits (12M)", "callback_data": "sub_ANALOG"},
            {"text": "💻 Digital Circuits (10M)", "callback_data": "sub_DIGITAL"}
        ],
        [
            {"text": "🎛️ Control Systems (10M)", "callback_data": "sub_CONTROL"},
            {"text": "📡 Communications (12M)", "callback_data": "sub_COMM"}
        ],
        [
            {"text": "🧲 Electromagnetics (10M)", "callback_data": "sub_EMFT"},
            {"text": "📐 Engineering Math (15M)", "callback_data": "sub_MATH"}
        ],
        [
            {"text": "🧠 General Aptitude (15M)", "callback_data": "sub_APT"}
        ]
    ]
}

SUBJECT_MAP = {
    "net": ("NET", "Networks, Signals & Systems"),
    "edc": ("EDC", "Electronic Devices (EDC)"),
    "analog": ("ANALOG", "Analog Circuits"),
    "digital": ("DIGITAL", "Digital Circuits"),
    "control": ("CONTROL", "Control Systems"),
    "comm": ("COMM", "Communications"),
    "emft": ("EMFT", "Electromagnetics (EMFT)"),
    "math": ("MATH", "Engineering Mathematics"),
    "apt": ("APT", "General Aptitude")
}

QUIZ_OPTIONS_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🅰️ Option A", "callback_data": "ans_A"},
            {"text": "🅱️ Option B", "callback_data": "ans_B"}
        ],
        [
            {"text": "🅲 Option C", "callback_data": "ans_C"},
            {"text": "🅳 Option D", "callback_data": "ans_D"}
        ]
    ]
}


def is_authorized(chat_id):
    """
    Fail-closed authorization check.
    Only allows access if TELEGRAM_CHAT_ID is defined and matches the sender.
    """
    auth_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not auth_id:
        return False
    return str(chat_id).strip() == auth_id


def send_chat_action(bot_token, chat_id, action="typing"):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
        data = urllib.parse.urlencode({"chat_id": chat_id, "action": action}).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        ctx = ssl.create_default_context()
        urllib.request.urlopen(req, context=ctx, timeout=5)
    except Exception:
        pass


def handle_command_start(chat_id, user_name, bot_token):
    config = load_config()
    current_subj = config.get("active_subject_name", "Networks, Signals & Systems")
    msg = f"""🎓 <b>Welcome, {user_name}!</b>
━━━━━━━━━━━━━━━━━━━━━
I am your <b>GATE 2027 ECE AI Study Mentor</b>.

📌 <b>Active Subject:</b> <b>{current_subj}</b>

🚀 <b>Core Preparation Superpowers:</b>
• 🎯 <b>Today's Mission:</b> Daily syllabus module, formulas & video class.
• 🏛️ <b>GATE PYQ:</b> Solve authentic past GATE questions (2018-2024).
• 📝 <b>Practice Quiz:</b> Interactive Telegram Quiz Polls with confetti!
• 🤖 <b>AI Practice:</b> Use <code>/practice</code> for fresh AI-generated problems.
• 📸 <b>Circuit Solver:</b> Snap and send a circuit photo anytime.
• ⚡ <b>Calculator:</b> Use <code>/calc</code> for exact resonance/RC/Op-amp math.
• 📈 <b>Analytics:</b> Track your accuracy and identified weak topics.

<i>Tap any button on your menu below to begin!</i>"""
    send_telegram_message(msg, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)


def handle_command_today(chat_id, bot_token):
    """
    Delivers today's mission. Returns True if successfully sent via Telegram.
    """
    config = load_config()
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE)
    active_module, all_modules = get_current_target(config, syllabus, tracker)
    days_left, _ = calculate_countdown(config.get("exam_target_date", "2027-02-06"))

    completed_count = sum(1 for m in all_modules if m.get("is_completed"))
    total_count = len(all_modules)

    msg = format_gate_message(
        active_module,
        days_left,
        tracker.get("current_streak_days", 1),
        completed_count,
        total_count
    )
    yt = active_module.get("youtube_class", {})
    action_markup = {
        "inline_keyboard": [
            [{"text": "▶️ Watch Lecture on YouTube", "url": yt.get("url", "https://youtube.com")}],
            [
                {"text": "📝 Practice Quiz", "callback_data": "act_pyq"},
                {"text": "✅ Mark Complete", "callback_data": "act_complete"}
            ]
        ]
    }
    ok, _ = send_telegram_message(msg, bot_token, chat_id, reply_markup=action_markup)
    return ok


def handle_command_status(chat_id, bot_token):
    config = load_config()
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE)
    active_module, all_modules = get_current_target(config, syllabus, tracker)
    days_left, _ = calculate_countdown(config.get("exam_target_date", "2027-02-06"))

    total_modules = len(all_modules)
    completed_count = sum(1 for m in all_modules if m.get("is_completed"))
    pct = (completed_count / total_modules * 100) if total_modules > 0 else 0

    filled = int(pct / 10)
    bar = "▰" * filled + "▱" * (10 - filled)

    msg = f"""📊 <b>GATE ECE 2027 Preparation Status</b>
━━━━━━━━━━━━━━━━━━━━━
⏳ <b>Countdown:</b> <b>{days_left} Days Remaining</b> (Feb 2027)
🔥 <b>Daily Study Streak:</b> <b>{tracker.get('current_streak_days', 1)} Days</b>
📈 <b>Syllabus Progress:</b> [{bar}] <b>{pct:.1f}%</b> ({completed_count}/{total_modules} Modules)

📚 <b>Active Subject:</b> <b>{config.get('active_subject_name', active_module.get('subject_name'))}</b>
📌 <b>Current Focus Module:</b>
[<code>{active_module.get('id')}</code>] <b>{active_module.get('title')}</b>
"""
    actions_markup = {
        "inline_keyboard": [
            [
                {"text": "🎯 View Today's Target", "callback_data": "act_today"},
                {"text": "📝 Practice Quiz", "callback_data": "act_pyq"}
            ]
        ]
    }
    send_telegram_message(msg, bot_token, chat_id, reply_markup=actions_markup)


def handle_command_complete(chat_id, bot_token):
    config = load_config()
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE)
    active_module, _ = get_current_target(config, syllabus, tracker)

    mid = active_module.get("id")
    tracker, is_new = update_streak_on_complete(mid)
    if is_new:
        msg = f"""🎉 <b>Module Completed!</b>
━━━━━━━━━━━━━━━━━━━━━
Awesome job! Module <code>[{mid}] {active_module.get('title')}</code> has been marked completed.

🔥 <b>Study Streak:</b> <b>{tracker['current_streak_days']} Days!</b>
Keep up the momentum. See you tonight at 7:00 PM IST! 🚀
"""
    else:
        msg = f"ℹ️ Module <code>[{mid}]</code> was already recorded as completed. Use <code>/status</code> to check progress."

    send_telegram_message(msg, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)


def handle_command_youtube(chat_id, bot_token):
    config = load_config()
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE)
    active_module, _ = get_current_target(config, syllabus, tracker)

    yt = active_module.get("youtube_class", {})
    pl = active_module.get("featured_playlist", {})
    title = yt.get("title", active_module.get("title", "Lecture Class"))
    url = yt.get("url", "https://youtube.com")
    educator = yt.get("educator", "Top GATE Faculty")

    msg = f"""📺 <b>Recommended YouTube Video Class</b>
━━━━━━━━━━━━━━━━━━━━━
📚 <b>Subject:</b> {active_module.get('subject_name')}
📌 <b>Topic:</b> [<code>{active_module.get('id')}</code>] <b>{active_module.get('title')}</b>
🎬 <b>Lecture:</b> <i>{title}</i>
👨‍🏫 <b>Educator:</b> <b>{educator}</b>

💡 <i>Tap a button below to launch the video in YouTube:</i>
"""
    buttons = [[{"text": "▶️ Open Video Lecture in YouTube", "url": url}]]
    if pl and pl.get("playlist_url"):
        buttons.append([{"text": "📁 Complete Subject Playlist", "url": pl.get("playlist_url")}])

    send_telegram_message(msg, bot_token, chat_id, reply_markup={"inline_keyboard": buttons})


def handle_command_formula(chat_id, bot_token):
    config = load_config()
    syllabus = get_syllabus()
    subj_code = config.get("active_subject_code", "NET")
    subj_name = config.get("active_subject_name", "Networks, Signals & Systems")

    formulas_list = []
    for s in syllabus.get("subjects", []):
        sid = s.get("id", "")
        if sid == subj_code or s.get("code") == subj_code or subj_code in sid:
            for m in s.get("modules", []):
                f_list = m.get("formulas", [])
                if f_list:
                    f_str = "\n".join([f"• <code>{f}</code>" for f in f_list])
                    formulas_list.append(f"📌 <b>[{m.get('id')}] {m.get('title')}:</b>\n{f_str}")

    if not formulas_list:
        formulas_body = "• Standard formulas are active in your daily module lessons."
    else:
        formulas_body = "\n\n".join(formulas_list[:4])

    msg = f"""💡 <b>High-Yield Formula Sheet: {subj_name}</b>
━━━━━━━━━━━━━━━━━━━━━
{formulas_body}
━━━━━━━━━━━━━━━━━━━━━
🎯 <i>Need step-by-step derivation or application for any formula? Ask me directly in chat!</i>
"""
    send_telegram_message(msg, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)


def handle_command_analytics(chat_id, bot_token):
    db_summary = get_analytics_summary()
    attempted = db_summary.get("total_attempts", 0)
    correct = db_summary.get("correct_count", 0)
    pct = db_summary.get("accuracy_pct", 0.0)

    subj_lines = ""
    for code, s in db_summary.get("by_subject", {}).items():
        att = s.get("attempted", 0)
        corr = s.get("correct", 0)
        spct = (corr / att * 100) if att > 0 else 0.0
        subj_lines += f"• <b>{code}:</b> {corr}/{att} correct ({spct:.0f}%)\n"

    if not subj_lines:
        subj_lines = "• <i>No questions answered yet. Tap '🏛️ GATE PYQ' or '📝 Practice Quiz' to begin!</i>\n"

    weak_list = db_summary.get("weak_topics", [])
    if weak_list:
        weak_str = "\n".join(weak_list)
    else:
        weak_str = "• <i>None detected yet! Great conceptual consistency.</i>"

    if pct >= 80 and attempted >= 5:
        rec = "🔥 <b>High Conceptual Accuracy:</b> Your foundational retention is solid. Prioritize practicing numerical answer type (NAT) questions to eliminate minor sign errors."
    elif pct >= 50:
        rec = "⚡ <b>Solid Foundation:</b> Target your revision specifically on the identified weak topics listed above before advancing to new modules."
    else:
        rec = "📖 <b>Concept Review Recommended:</b> Review the recommended YouTube classes thoroughly before taking quizzes to cement the core principles."

    msg = f"""📈 <b>GATE ECE Performance Analytics</b>
━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Total Problems Attempted:</b> {attempted}
✅ <b>Correct Answers:</b> {correct}
📊 <b>Overall Accuracy:</b> <b>{pct:.1f}%</b>

📚 <b>Subject-wise Accuracy:</b>
{subj_lines}
⚠️ <b>Top Identified Weak Topics:</b>
{weak_str}
━━━━━━━━━━━━━━━━━━━━━
💡 <b>AI Tutor Action Plan:</b>
{rec}
"""
    send_telegram_message(msg, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)


def handle_command_calc(chat_id, text, bot_token):
    parts = text.strip().split()
    if len(parts) < 2:
        msg = """⚡ <b>GATE ECE Engineering Calculator</b>
━━━━━━━━━━━━━━━━━━━━━
Zero hallucinations. 100% deterministic mathematical calculations:

• <b>Resonance Frequency:</b>
  <code>/calc res L C</code> (e.g. <code>/calc res 0.1 10u</code>)
• <b>RC Cutoff Frequency:</b>
  <code>/calc rc R C</code> (e.g. <code>/calc rc 1k 1u</code>)
• <b>Op-Amp Gain (Ideal Inverting/Non-inverting):</b>
  <code>/calc opamp R1 Rf</code> (e.g. <code>/calc opamp 10k 100k</code>)
• <b>Decibel (dB) Gain:</b>
  <code>/calc db 100</code>
"""
        send_telegram_message(msg, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)
        return

    def parse_val(s):
        s = s.lower().replace("k", "e3").replace("m", "e-3").replace("u", "e-6").replace("n", "e-9").replace("p", "e-12")
        return float(s)

    subcmd = parts[1].lower()
    try:
        if subcmd in ("res", "resonance") and len(parts) >= 4:
            L = parse_val(parts[2])
            C = parse_val(parts[3])
            if L <= 0 or C <= 0:
                msg = "⚠️ <b>Math Error:</b> L and C must be strictly positive ($L > 0, C > 0$)."
            else:
                w0 = 1.0 / math.sqrt(L * C)
                f0 = w0 / (2.0 * math.pi)
                msg = f"""⚡ <b>Resonance Calculation:</b>
━━━━━━━━━━━━━━━━━━━━━
L = {L:.2e} H | C = {C:.2e} F

• <b>Angular Frequency (ω₀):</b> <code>{w0:,.2f} rad/s</code>
• <b>Resonant Frequency (f₀):</b> <code>{f0:,.2f} Hz</code> ({f0/1000:.2f} kHz)
• <b>Formula:</b> ω₀ = 1/√(LC), f₀ = ω₀/(2π)
<i>Note: Standard lossless LC / series-parallel RLC model.</i>
"""
        elif subcmd == "rc" and len(parts) >= 4:
            R = parse_val(parts[2])
            C = parse_val(parts[3])
            if R <= 0 or C <= 0:
                msg = "⚠️ <b>Math Error:</b> R and C must be strictly positive ($R > 0, C > 0$)."
            else:
                tau = R * C
                fc = 1.0 / (2.0 * math.pi * tau)
                msg = f"""⚡ <b>RC Network Calculation:</b>
━━━━━━━━━━━━━━━━━━━━━
R = {R:.2e} Ω | C = {C:.2e} F

• <b>Time Constant (τ):</b> <code>{tau*1e3:.3f} ms</code> ({tau:.2e} s)
• <b>3-dB Cutoff Frequency (fc):</b> <code>{fc:,.2f} Hz</code> ({fc/1000:.2f} kHz)
• <b>Formula:</b> τ = RC, fc = 1/(2πRC)
<i>Note: Assuming first-order single-pole RC network.</i>
"""
        elif subcmd == "opamp" and len(parts) >= 4:
            R1 = parse_val(parts[2])
            Rf = parse_val(parts[3])
            if R1 <= 0 or Rf < 0:
                msg = "⚠️ <b>Math Error:</b> R1 must be > 0 and Rf >= 0."
            else:
                inv_gain = - (Rf / R1)
                non_inv_gain = 1 + (Rf / R1)
                db_val = 20 * math.log10(abs(inv_gain)) if abs(inv_gain) > 0 else 0
                msg = f"""⚡ <b>Op-Amp Gain Calculation:</b>
━━━━━━━━━━━━━━━━━━━━━
R1 = {R1:,.0f} Ω | Rf = {Rf:,.0f} Ω

• <b>Inverting Gain (Av):</b> <code>{inv_gain:.2f}</code> (Phase: 180°)
• <b>Non-Inverting Gain (Av):</b> <code>{non_inv_gain:.2f}</code> (Phase: 0°)
• <b>Inverting Gain (dB):</b> <code>{db_val:.2f} dB</code>
<i>Note: Assuming ideal op-amp in standard negative feedback linear operation.</i>
"""
        elif subcmd == "db" and len(parts) >= 3:
            val = parse_val(parts[2])
            if val <= 0:
                msg = "⚠️ <b>Math Error:</b> Ratio for decibels must be strictly positive ($X > 0$)."
            else:
                v_db = 20 * math.log10(val)
                p_db = 10 * math.log10(val)
                msg = f"""⚡ <b>Decibel Conversion:</b>
━━━━━━━━━━━━━━━━━━━━━
Ratio: {val}

• <b>For Voltage / Current / Field Ratio (20 log₁₀ X):</b> <code>{v_db:.2f} dB</code>
• <b>For Power Ratio (10 log₁₀ X):</b> <code>{p_db:.2f} dB</code>
"""
        else:
            msg = "⚠️ <i>Invalid arguments. Type <code>/calc</code> for usage guide.</i>"
    except Exception as e:
        msg = f"⚠️ Calculation error: {e}"

    send_telegram_message(msg, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)


def handle_command_pyq(chat_id, bot_token):
    """
    Delivers an authentic, historical GATE ECE Previous Year Question from curated paper bank.
    """
    config = load_config()
    subj_code = config.get("active_subject_code", "NET")
    q = get_curated_pyq(subj_code)

    opts_text = "\n".join([f"  <b>{chr(65+i)})</b> {opt}" for i, opt in enumerate(q["options"])])

    msg = f"""🏛️ <b>Authentic GATE ECE {q['year']} ({q['marks']} Marks)</b>
━━━━━━━━━━━━━━━━━━━━━
📜 <b>Source:</b> <i>{q.get('source', 'Official GATE Paper')} ({q.get('question_number', 'PYQ')})</i>
📚 <b>Subject:</b> {q['subject_code']} | 📌 <b>Topic:</b> {q['topic']}

{q['question']}

{opts_text}
━━━━━━━━━━━━━━━━━━━━━
💡 <i>Tap your answer below to verify against official GATE key & derivation:</i>"""

    poll_markup = {
        "inline_keyboard": [
            [
                {"text": "🅰️ Option A", "callback_data": f"pyq_{q['id']}_0"},
                {"text": "🅱️ Option B", "callback_data": f"pyq_{q['id']}_1"}
            ],
            [
                {"text": "🅲 Option C", "callback_data": f"pyq_{q['id']}_2"},
                {"text": "🅳 Option D", "callback_data": f"pyq_{q['id']}_3"}
            ]
        ]
    }
    send_telegram_message(msg, bot_token, chat_id, reply_markup=poll_markup)


def handle_command_practice(chat_id, bot_token):
    """
    Generates a structured, syllabus-constrained practice question with deterministic answer verification.
    """
    config = load_config()
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE)
    active_module, _ = get_current_target(config, syllabus, tracker)

    subj_name = config.get("active_subject_name", "Networks, Signals & Systems")
    subj_code = config.get("active_subject_code", "NET")
    allowed_topics = active_module.get("key_concepts", [])

    send_chat_action(bot_token, chat_id, "typing")
    data, err = generate_practice_question(
        active_subject_name=subj_name,
        active_subject_code=subj_code,
        active_module_id=active_module.get("id", "NET-M01"),
        allowed_topics=allowed_topics,
        chat_id=chat_id
    )

    if err:
        send_telegram_message(err, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)
        return

    q_id = f"prac_{int(time.time()*1000) % 10000000}"
    save_practice_question(
        question_id=q_id,
        chat_id=chat_id,
        subject_code=subj_code,
        module_id=active_module.get("id", "NET-M01"),
        topic_name=data.get("topic_name", active_module.get("title")),
        question=data["question"],
        options=data["options"],
        correct_id=data["correct_option_id"],
        explanation=data["explanation"]
    )

    opts_text = "\n".join([f"  <b>{chr(65+i)})</b> {opt}" for i, opt in enumerate(data["options"])])

    msg = f"""🤖 <b>AI-Generated GATE Practice Problem</b>
━━━━━━━━━━━━━━━━━━━━━
📚 <b>Subject:</b> {subj_name}
📌 <b>Topic:</b> <b>{data.get('topic_name', active_module.get('title'))}</b>

{data['question']}

{opts_text}
━━━━━━━━━━━━━━━━━━━━━
💡 <i>Tap your option below to check your answer and view the step-by-step derivation:</i>"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "🅰️ Option A", "callback_data": f"prac_{q_id}_0"},
                {"text": "🅱️ Option B", "callback_data": f"prac_{q_id}_1"}
            ],
            [
                {"text": "🅲 Option C", "callback_data": f"prac_{q_id}_2"},
                {"text": "🅳 Option D", "callback_data": f"prac_{q_id}_3"}
            ]
        ]
    }
    send_telegram_message(msg, bot_token, chat_id, reply_markup=markup)


def handle_command_quiz_poll(chat_id, bot_token):
    config = load_config()
    subj_name = config.get("active_subject_name", "Networks, Signals & Systems")
    subj_code = config.get("active_subject_code", "NET")
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE)
    active_module, _ = get_current_target(config, syllabus, tracker)

    send_chat_action(bot_token, chat_id, "typing")
    quiz_data = generate_native_quiz_poll(
        active_subject_name=subj_name,
        active_subject_code=subj_code,
        active_module_id=active_module.get("id", "NET-M01"),
        allowed_topics=active_module.get("key_concepts", [])
    )

    ok, res = send_telegram_poll(
        chat_id=chat_id,
        question=quiz_data["question"],
        options=quiz_data["options"],
        correct_option_id=quiz_data["correct_option_id"],
        explanation=quiz_data.get("explanation", ""),
        bot_token=bot_token
    )
    if ok:
        poll_id = res.get("result", {}).get("poll", {}).get("id")
        if poll_id:
            save_active_poll(
                poll_id=poll_id,
                subject_code=subj_code,
                correct_id=quiz_data["correct_option_id"],
                question=quiz_data.get("question", ""),
                module_id=quiz_data.get("module_id", active_module.get("id")),
                topic_name=quiz_data.get("topic_name", active_module.get("title"))
            )


def handle_poll_answer(poll_ans, bot_token):
    """
    Called when a student votes on a Telegram Quiz Poll.
    Deduplicates attempt and persists in SQLite. Unknown polls are cleanly ignored.
    """
    poll_id = str(poll_ans.get("poll_id", ""))
    user_id = str(poll_ans.get("user", {}).get("id", ""))
    selected_ids = poll_ans.get("option_ids", [])
    if not selected_ids:
        return

    chosen_id = selected_ids[0]
    is_correct, subj_code, topic_name = record_poll_attempt(poll_id, user_id, chosen_id)
    if subj_code:
        print(f"Recorded poll answer in SQLite: poll_id={poll_id}, subj={subj_code}, topic='{topic_name}', correct={is_correct}")


def handle_command_subject(chat_id, text, bot_token):
    config = load_config()
    raw = text.strip()
    cmd_lower = raw.lower()

    # List of triggers that simply request the menu
    menu_triggers = [
        "/subject", "subject", "📚 switch subject", "switch subject",
        "change subject", "choose subject", "subjects", "/subjects"
    ]

    target_arg = None
    if cmd_lower not in menu_triggers:
        if cmd_lower.startswith("/subject "):
            target_arg = cmd_lower.replace("/subject ", "").strip()
        elif cmd_lower.startswith("subject "):
            target_arg = cmd_lower.replace("subject ", "").strip()
        elif len(raw.split()) > 1:
            target_arg = raw.split()[1].strip().lower()

    # Numeric shortcuts 1-9
    num_to_key = {
        "1": "net",
        "2": "edc",
        "3": "analog",
        "4": "digital",
        "5": "control",
        "6": "comm",
        "7": "emft",
        "8": "math",
        "9": "apt"
    }
    if target_arg in num_to_key:
        target_arg = num_to_key[target_arg]

    if not target_arg:
        current_name = config.get("active_subject_name", "Networks, Signals & Systems")
        msg = f"""📚 <b>GATE ECE 2027 Subject Selection Menu</b>
━━━━━━━━━━━━━━━━━━━━━
📌 <b>Current Active Subject:</b>
👉 <b>{current_name}</b>

💡 <i>Select a subject to target today's classes, formulas, and quizzes:</i>"""
        send_telegram_message(msg, bot_token, chat_id, reply_markup=SUBJECT_INLINE_KEYBOARD)
        return

    for key, (code, full_name) in SUBJECT_MAP.items():
        if target_arg in (key, code.lower()):
            config["active_subject_code"] = code
            config["active_subject_name"] = full_name
            save_config(config)
            clear_chat_history(chat_id)

            syllabus = get_syllabus()
            tracker = load_json(TRACKER_FILE)
            active_module, _ = get_current_target(config, syllabus, tracker)

            msg = f"""✅ <b>Switched to {full_name} [{code}]!</b>
━━━━━━━━━━━━━━━━━━━━━
📌 <b>Next Target Module:</b>
[<code>{active_module.get('id')}</code>] <b>{active_module.get('title')}</b>

⏰ <i>Evening 7:00 PM dispatches will now focus on {full_name}!</i>"""
            send_telegram_message(msg, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)
            return

    send_telegram_message("⚠️ Unknown subject code. Use <code>/subject</code> to see the list.", bot_token, chat_id)


def handle_callback_query(cb, bot_token):
    cb_id = cb["id"]
    from_user = cb.get("from", {})
    chat_id = from_user.get("id")
    data = cb.get("data", "")

    if not is_authorized(chat_id):
        answer_callback_query(cb_id, bot_token, text="Access restricted.")
        return

    if data.startswith("sub_"):
        subj_code = data.replace("sub_", "").lower()
        if subj_code in SUBJECT_MAP:
            code, full_name = SUBJECT_MAP[subj_code]
            config = load_config()
            config["active_subject_code"] = code
            config["active_subject_name"] = full_name
            save_config(config)
            clear_chat_history(chat_id)

            answer_callback_query(cb_id, bot_token, text=f"Switched to {full_name}!")
            syllabus = get_syllabus()
            tracker = load_json(TRACKER_FILE)
            active_module, _ = get_current_target(config, syllabus, tracker)

            msg = f"""✅ <b>Active Subject Switched to:</b>
👉 <b>{full_name}</b> <code>[{code}]</code>
━━━━━━━━━━━━━━━━━━━━━
📌 <b>Current Focus Module:</b>
[<code>{active_module.get('id')}</code>] <b>{active_module.get('title')}</b>

⏰ <i>Tonight's 7:00 PM automated study brief will focus on {code}!</i>"""
            actions_kb = {
                "inline_keyboard": [
                    [
                        {"text": "🎯 View Today's Target", "callback_data": "act_today"},
                        {"text": "📝 Practice Quiz", "callback_data": "act_pyq"}
                    ],
                    [
                        {"text": "📺 Watch YouTube Class", "url": active_module.get("youtube_class", {}).get("url", "https://youtube.com")}
                    ]
                ]
            }
            send_telegram_message(msg, bot_token, chat_id, reply_markup=actions_kb)
        else:
            answer_callback_query(cb_id, bot_token, text="Unknown subject.")
    elif data == "act_today":
        answer_callback_query(cb_id, bot_token)
        handle_command_today(chat_id, bot_token)
    elif data == "act_pyq":
        answer_callback_query(cb_id, bot_token)
        handle_command_quiz_poll(chat_id, bot_token)
    elif data == "act_status":
        answer_callback_query(cb_id, bot_token)
        handle_command_status(chat_id, bot_token)
    elif data == "act_complete":
        answer_callback_query(cb_id, bot_token, text="Completed!")
        handle_command_complete(chat_id, bot_token)
    elif data.startswith("pyq_"):
        answer_callback_query(cb_id, bot_token, text="Answer evaluated!")
        parts = data.split("_")
        q_id = "_".join(parts[1:-1])
        chosen_id = int(parts[-1])
        match_q = next((q for q in CURATED_PYQ_BANK if q["id"] == q_id), None)
        if match_q:
            corr_id = match_q["correct_option_id"]
            is_corr = (chosen_id == corr_id)
            record_pyq_attempt(
                question_id=q_id,
                user_id=str(chat_id),
                subject_code=match_q["subject_code"],
                module_id=match_q.get("module_id", "NET-M01"),
                topic_name=match_q["topic"],
                chosen_id=chosen_id,
                is_correct=is_corr
            )

            status_icon = "✅ <b>CORRECT!</b>" if is_corr else "❌ <b>INCORRECT</b>"
            resp = f"""{status_icon}
━━━━━━━━━━━━━━━━━━━━━
🏛️ <b>Official GATE ECE {match_q['year']} Answer:</b> <b>Option {chr(65+corr_id)}</b> ({match_q['options'][corr_id]})

💡 <b>Detailed Derivation:</b>
{match_q['explanation']}"""
            send_telegram_message(resp, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)
    elif data.startswith("prac_"):
        answer_callback_query(cb_id, bot_token, text="Practice answer evaluated!")
        parts = data.split("_")
        q_id = "_".join(parts[1:-1])
        chosen_id = int(parts[-1])
        is_corr, pq, topic_name = record_practice_attempt(q_id, str(chat_id), chosen_id)
        if pq:
            corr_id = pq["correct_id"]
            status_icon = "✅ <b>CORRECT!</b>" if is_corr else "❌ <b>INCORRECT</b>"
            resp = f"""{status_icon}
━━━━━━━━━━━━━━━━━━━━━
📌 <b>Topic:</b> {topic_name}
🎯 <b>Correct Answer:</b> <b>Option {chr(65+corr_id)}</b> ({pq['options'][corr_id]})

💡 <b>Step-by-Step Derivation:</b>
{pq['explanation']}"""
            send_telegram_message(resp, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)


def handle_message(update, bot_token):
    msg_obj = update.get("message", {})
    chat = msg_obj.get("chat", {})
    chat_id = chat.get("id")
    from_user = msg_obj.get("from", {})
    user_name = from_user.get("first_name", "Student")
    text = (msg_obj.get("text") or "").strip()

    if not chat_id:
        return

    # Fail-closed authorization check
    if not is_authorized(chat_id):
        send_telegram_message("⛔ <b>Access Restricted:</b> This GATE 2027 ECE Study Assistant is a private tutor linked to an authorized student account.", bot_token, chat_id)
        return

    # Multimodal Circuit / Photo Doubt Solving
    if "photo" in msg_obj:
        photos = msg_obj.get("photo", [])
        if photos:
            send_chat_action(bot_token, chat_id, "typing")
            best_photo = photos[-1]
            file_id = best_photo.get("file_id")
            caption = (msg_obj.get("caption") or "").strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Photo received from {user_name} (caption: '{caption}')")
            img_bytes = download_telegram_file(file_id, bot_token)
            if img_bytes:
                ai_reply = generate_gate_ai_vision_reply(caption, img_bytes, chat_id=chat_id)
                send_telegram_message(ai_reply, bot_token, chat_id, reply_markup=MAIN_KEYBOARD)
            else:
                send_telegram_message("⚠️ Could not download image from Telegram. Please retry.", bot_token, chat_id, reply_markup=MAIN_KEYBOARD)
        return

    if not text:
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Message from {user_name} ({chat_id}): {text}")
    cmd = text.lower().strip()

    config = load_config()
    syllabus = get_syllabus()
    tracker = load_json(TRACKER_FILE)
    active_module, _ = get_current_target(config, syllabus, tracker)
    context_info = f"Subject: {active_module.get('subject_name')} | Module: {active_module.get('id')} - {active_module.get('title')}"

    if cmd in ("/start", "start"):
        handle_command_start(chat_id, user_name, bot_token)
    elif cmd in ("/subject", "subject", "📚 switch subject", "switch subject", "change subject", "choose subject") or cmd.startswith("/subject ") or cmd.startswith("subject "):
        handle_command_subject(chat_id, text, bot_token)
    elif cmd in [str(i) for i in range(1, 10)]:
        handle_command_subject(chat_id, f"/subject {cmd}", bot_token)
    elif cmd in ("/today", "today", "🎯 today's mission", "today mission", "what should i study today", "what to study today", "what should i study", "today target", "today's target"):
        handle_command_today(chat_id, bot_token)
    elif cmd in ("/youtube", "youtube", "📺 youtube class", "give me a yt recommendation", "yt recommendation", "lecture class", "video lecture", "video class", "yt", "youtube recommendation"):
        handle_command_youtube(chat_id, bot_token)
    elif cmd in ("/formula", "formula", "💡 formula sheet", "formula sheet", "formulas", "formula card", "/formulas"):
        handle_command_formula(chat_id, bot_token)
    elif cmd in ("/analytics", "analytics", "📈 score & stats", "score & stats", "score", "stats", "my score", "/score", "/stats"):
        handle_command_analytics(chat_id, bot_token)
    elif cmd in ("/status", "status", "📊 progress bar", "progress bar", "progress", "streak", "status report", "my progress"):
        handle_command_status(chat_id, bot_token)
    elif cmd in ("/complete", "complete", "✅ mark done", "done", "mark complete", "completed"):
        handle_command_complete(chat_id, bot_token)
    elif cmd in ("/quiz", "quiz", "📝 practice quiz", "practice quiz", "/poll", "poll", "quiz test"):
        handle_command_quiz_poll(chat_id, bot_token)
    elif cmd in ("/pyq", "pyq", "🏛️ gate pyq", "previous year question", "gate question"):
        handle_command_pyq(chat_id, bot_token)
    elif cmd in ("/practice", "practice", "ai practice", "generate question", "give me a question", "give me new question", "new question", "another question", "practice question", "next question", "give me another question"):
        handle_command_practice(chat_id, bot_token)
    elif cmd.startswith("/calc") or cmd.startswith("calc"):
        handle_command_calc(chat_id, text, bot_token)
    elif cmd in ("/help", "help"):
        handle_command_start(chat_id, user_name, bot_token)
    else:
        # Standard technical doubt or answer submission
        send_chat_action(bot_token, chat_id, "typing")

        reply_to = msg_obj.get("reply_to_message")
        enriched_text = text

        if reply_to:
            if "poll" in reply_to:
                p = reply_to["poll"]
                q_text = p.get("question", "")
                opts = [o.get("text", "") for o in p.get("options", [])]
                opts_str = " | ".join(opts) if opts else ""
                enriched_text = (
                    f"Regarding this Quiz Poll question:\n"
                    f"\"{q_text}\"\n"
                    f"Options: {opts_str}\n\n"
                    f"Student asks: {text}"
                )
            elif "text" in reply_to:
                q_text = reply_to.get("text", "")
                if len(q_text) > 800:
                    q_text = q_text[:800] + "..."
                enriched_text = (
                    f"Regarding your previous message:\n"
                    f"\"{q_text}\"\n\n"
                    f"Student asks: {text}"
                )
        else:
            generic_triggers = (
                "tell me in detail", "tell me in detaile", "explain", "explain this",
                "how to solve", "how to solve this", "solution", "why", "detail",
                "details", "explain in detail", "show steps", "show derivation",
                "explain the answer", "how"
            )
            if any(cmd.startswith(t) or cmd == t for t in generic_triggers):
                last_q, last_topic = get_latest_question()
                if last_q:
                    enriched_text = (
                        f"The student is asking for a detailed step-by-step explanation/derivation of the recent problem ({last_topic}):\n"
                        f"Problem: \"{last_q}\"\n\n"
                        f"Student's query: {text}"
                    )

        ai_reply = generate_gate_ai_reply(enriched_text, chat_id=chat_id, context_info=context_info)
        has_mcq = all(k in ai_reply for k in ["(A)", "(B)", "(C)", "(D)"]) or all(k in ai_reply for k in ["A)", "B)", "C)", "D)"])
        markup = QUIZ_OPTIONS_KEYBOARD if has_mcq else MAIN_KEYBOARD
        send_telegram_message(ai_reply, bot_token, chat_id, reply_markup=markup)


def daily_scheduler_thread(bot_token, target_chat_id):
    """
    Background worker that triggers the daily 7:00 PM (19:00 IST) dispatch.
    Restart-safe using SQLite scheduler_state. Verifies delivery before recording sent date.
    """
    print("⏰ Restart-Safe 7:00 PM IST Daily Scheduler active.")

    while True:
        try:
            now = datetime.now(IST)
            today_str = now.strftime("%Y-%m-%d")
            last_dispatched = get_last_dispatch_date()

            # Triggers at or after 19:00 IST if not already dispatched today
            if now.hour >= 19 and last_dispatched != today_str:
                print(f"\n🔔 [7:00 PM IST] Triggering automated daily study mission for {today_str}...")
                delivered = handle_command_today(target_chat_id, bot_token)
                if delivered:
                    set_last_dispatch_date(today_str)
                    print(f"Successfully recorded dispatch for {today_str} in SQLite.")
                else:
                    print("Dispatch failed to send via Telegram; will retry on next check.")

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
    <p style="color: #10b981; font-size: 20px; font-weight: bold;">● Status: 24/7 Cloud Service Online (v3.1 Production)</p>
    <p>Bot: <b>@Varshith772bot</b></p>
    <p style="color: #94a3b8; font-size: 13px;">Daily 7:00 PM IST Automation & AI Chat Active</p>
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
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    target_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token:
        print("❌ Fatal: TELEGRAM_BOT_TOKEN environment variable missing.")
        sys.exit(1)

    if not target_chat_id:
        print("⚠️ Warning: TELEGRAM_CHAT_ID environment variable missing. Fail-closed mode active.")

    print("=" * 65)
    print("  🚀 GATE 2027 TELEGRAM AI BOT SERVICE STARTED (v3.1 Production)")
    print(f"  👤 Authorized Chat ID: {target_chat_id}")
    print("  ⚡ Listening for incoming messages & doubts...")
    print("=" * 65)

    t_http = threading.Thread(target=start_health_server, daemon=True)
    t_http.start()

    if target_chat_id:
        t = threading.Thread(target=daily_scheduler_thread, args=(bot_token, target_chat_id), daemon=True)
        t.start()

    offset = 0
    ctx = ssl.create_default_context()

    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=20"
            req = urllib.request.Request(url, headers={"User-Agent": "GATE2027Bot/3.1"})
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        try:
                            if "callback_query" in update:
                                threading.Thread(target=handle_callback_query, args=(update["callback_query"], bot_token), daemon=True).start()
                            elif "poll_answer" in update:
                                threading.Thread(target=handle_poll_answer, args=(update["poll_answer"], bot_token), daemon=True).start()
                            elif "message" in update:
                                threading.Thread(target=handle_message, args=(update, bot_token), daemon=True).start()
                        except Exception as item_err:
                            print(f"Update handling notice: {item_err}")
        except urllib.error.URLError:
            time.sleep(1)
        except Exception as e:
            print(f"Polling loop notice: {e}")
            time.sleep(1)


if __name__ == "__main__":
    run_bot()