"""
GATE 2027 AI Conversational Engine
-----------------------------------
Supports:
1. Google Gemini API (Free tier: gemini-1.5-flash / gemini-2.0-flash via Google AI Studio)
2. Groq Cloud API (Free tier: llama-3.3-70b-versatile via Groq Console)
3. Built-in GATE Syllabus & Topic Retrieval Knowledge Base (Zero-key instant fallback)
"""

import os
import sys
import json
import ssl
import re
import urllib.request
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
DATA_DIR = BASE_DIR / "data"

GATE_SYSTEM_PROMPT = """You are "GATE Mentor AI", an elite GATE Computer Science and Data Science tutor and academic coach for GATE 2027.
Your goal is to help the student master concepts, clarify doubts, learn formulas, and practice Previous Year Questions (PYQs).

Guidelines:
1. Be encouraging, concise, rigorous, and direct. Keep explanations punchy and exam-oriented.
2. For math/algorithms, explain the intuition, show formulas cleanly, and mention common GATE traps (e.g. edge cases, 0-indexing vs 1-indexing, worst-case vs average-case).
3. If the user asks for a PYQ or practice question, give a realistic GATE question (MCQ, MSQ, or NAT style), provide 4 options (if MCQ), and wait for their answer before giving the full explanation, or provide a spoiler/hint.
4. Format output neatly using Telegram-compatible HTML tags: <b>bold</b>, <i>italic</i>, <code>code</code>, <pre>code block</pre>. Do NOT use Markdown asterisks if HTML is active, or use clean plain text with standard bullets.
"""


def load_config():
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_ai_credentials():
    cfg = load_config()
    ai_cfg = cfg.get("ai_engine", {})
    gemini_key = ai_cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    groq_key = ai_cfg.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
    provider = ai_cfg.get("provider", "auto")
    return provider, gemini_key.strip(), groq_key.strip()


def call_gemini(prompt, api_key):
    """
    Calls Google Gemini REST API.
    Free tier allows up to 1,500 requests per day via Google AI Studio.
    Tries gemini-1.5-flash, gemini-2.0-flash, or gemini-2.5-flash.
    """
    candidate_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-pro"]
    last_err = None

    for model in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{GATE_SYSTEM_PROMPT}\n\nStudent Doubt/Request:\n{prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 1024
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
        except urllib.error.HTTPError as e:
            last_err = e
            # If model name not found, try next candidate model
            if e.code in (400, 404):
                continue
            raise e
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise last_err
    return "Could not generate response from Gemini."


def call_groq(prompt, api_key, model="llama-3.3-70b-versatile"):
    """
    Calls Groq Cloud API (Free tier: ultra fast Llama 3.3 70B).
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": GATE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 1024
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
        res_json = json.loads(resp.read().decode("utf-8"))
        choices = res_json.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return "Could not parse response from Groq."


def search_local_syllabus(query):
    """
    Smart keyword matcher against local GATE CS & DA syllabus database.
    """
    query_lower = query.lower()
    cs_file = DATA_DIR / "syllabus_cs.json"
    if not cs_file.exists():
        return None

    try:
        with open(cs_file, "r", encoding="utf-8") as f:
            syllabus = json.load(f)
    except Exception:
        return None

    matches = []
    for subject in syllabus.get("subjects", []):
        for module in subject.get("modules", []):
            score = 0
            # Match module title or ID
            if module.get("id", "").lower() in query_lower:
                score += 10
            for w in module.get("title", "").lower().split():
                if len(w) > 3 and w in query_lower:
                    score += 3
            # Match topics
            for topic in module.get("topics", []):
                for tw in topic.lower().split():
                    if len(tw) > 3 and tw in query_lower:
                        score += 2
            if score > 0:
                matches.append((score, subject, module))

    matches.sort(key=lambda x: x[0], reverse=True)
    if matches:
        _, best_subj, best_mod = matches[0]
        return best_subj, best_mod
    return None


def generate_syllabus_fallback(query):
    """
    Provides intelligent local answer when no cloud API key is configured yet.
    """
    result = search_local_syllabus(query)
    if result:
        subj, mod = result
        vids = mod.get("recommended_videos", [])
        vid_text = ""
        for i, v in enumerate(vids, 1):
            vid_text += f"\n  ▶ <a href=\"{v['url']}\"><b>{v['title']}</b></a>"

        resp = f"""📚 <b>GATE Topic Reference: [{mod.get('id')}] {mod.get('title')}</b>
━━━━━━━━━━━━━━━━━━━━━
📖 <b>Subject:</b> {subj.get('name')} (Weightage: {subj.get('weightage')})

💡 <b>Key Concept Takeaway:</b>
<i>{mod.get('key_points')}</i>

🎯 <b>PYQ Target:</b> {mod.get('pyq_target')}

📺 <b>Recommended Classes:</b>{vid_text}
📁 <a href=\"{subj.get('featured_playlist', {}).get('url', 'https://youtube.com')}\">Full Subject Playlist</a>
━━━━━━━━━━━━━━━━━━━━━
<i>💡 Want full conversational AI for open doubts? Send your 100% free Gemini API key:</i>
<code>/setkey YOUR_GEMINI_KEY</code>
<i>(Get one in 10 seconds at: aistudio.google.com/app/apikey)</i>
"""
        return resp

    # General fallback
    return f"""🤖 <b>GATE 2027 Study Assistant</b>
━━━━━━━━━━━━━━━━━━━━━
I received your doubt: <i>"{query}"</i>

To unlock full interactive conversational explanations for any GATE question or code doubt, connect your free Google Gemini API key:

1. Visit: <b>https://aistudio.google.com/app/apikey</b> (100% free, no credit card needed).
2. Create an API key.
3. Send it directly here in chat:
   <code>/setkey YOUR_API_KEY</code>

✨ <b>Quick Commands Available Right Now:</b>
• <code>/today</code> - Tonight's 7:00 PM lecture class & goals
• <code>/status</code> - Exam countdown & syllabus progress
• <code>/pyq</code> - Practice questions on current topic
• <code>/complete</code> - Mark today's module done & add to streak
"""


def generate_gate_ai_reply(query):
    """
    Main entrypoint: routes to Gemini, Groq, or local intelligent fallback.
    """
    provider, gemini_key, groq_key = get_ai_credentials()

    # Try Gemini first if key available
    if gemini_key:
        try:
            raw_answer = call_gemini(query, gemini_key)
            return clean_response_for_telegram(raw_answer)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if "leaked" in err_body.lower() or e.code == 403:
                return """⚠️ <b>Google Gemini Security Alert:</b>
━━━━━━━━━━━━━━━━━━━━━
Your API key (<code>""" + gemini_key[:10] + """...</code>) was permanently <b>blocked by Google</b> because it was detected as leaked on GitHub.

👉 <b>How to fix in 30 seconds:</b>
1. Open: <b>https://aistudio.google.com/app/apikey</b>
2. Delete the old key.
3. Click <b>+ Create API key</b> to generate a fresh new key.
4. Send your new key here in chat:
   <code>/setkey YOUR_NEW_API_KEY</code>"""
            print(f"Gemini API Error {e.code}: {err_body}")
        except Exception as e:
            print(f"Gemini exception: {e}")

    # Try Groq if key available
    if groq_key:
        try:
            raw_answer = call_groq(query, groq_key)
            return clean_response_for_telegram(raw_answer)
        except Exception as e:
            pass

    # Fallback to local syllabus intelligence
    return generate_syllabus_fallback(query)


def clean_response_for_telegram(text):
    """
    Ensures safe formatting for Telegram HTML parse mode.
    """
    # If text has unescaped HTML characters that might break Telegram HTML parser, escape them or convert basic markdown
    # Convert markdown headers ### to bold
    text = re.sub(r"^###\s*(.*)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s*(.*)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^#\s*(.*)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    # Convert **bold** to <b>bold</b>
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    # Convert *italic* to <i>italic</i>
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    # Convert `code` to <code>code</code>
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text.strip()


def generate_pyq_question():
    """
    Generates a GATE practice question on the active module.
    """
    cfg = load_config()
    tracker_file = DATA_DIR / "progress_tracker.json"
    tracker = {}
    if tracker_file.exists():
        with open(tracker_file, "r", encoding="utf-8") as f:
            tracker = json.load(f)

    in_prog = tracker.get("in_progress_module", "DM-01")
    prompt = f"Generate 1 high-yield GATE Computer Science practice question on topic [{in_prog}]. Give 4 options (A, B, C, D). Mention whether it is MCQ or MSQ. Provide the correct answer and a step-by-step explanation inside an HTML spoiler tag or clearly separated at the bottom."

    return generate_gate_ai_reply(prompt)


if __name__ == "__main__":
    test_query = sys.argv[1] if len(sys.argv) > 1 else "Explain Master Theorem for GATE CS"
    print("Testing AI Engine with query:", test_query)
    print("\n--- RESPONSE ---\n")
    print(generate_gate_ai_reply(test_query))
