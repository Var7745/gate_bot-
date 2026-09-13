"""
GATE 2027 ECE AI Engine & Multimodal Doubt Solver (v3 Production)
-----------------------------------------------------------------
Features:
1. Google Gemini 2.5 Flash / Flash Latest with structured ECE pedagogy
2. Strictly environment-based credentials (zero secrets in config.json)
3. Multimodal Circuit/Photo Doubt Solving with 5-step engineering framework
4. Syllabused-constrained native quiz polls and practice questions
5. Per-user request rate limiting (12 queries/minute)
6. SQLite-backed persistent multi-turn conversational memory
7. Safe student-facing error messages (no URL or exception leaks)
"""

import os
import sys
import json
import time
import ssl
import re
import base64
import random
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
CONFIG_FILE = BASE_DIR / "config.json"
SYLLABUS_FILE = DATA_DIR / "syllabus_ec.json"

sys.path.insert(0, str(BASE_DIR / "scripts"))
from db_manager import add_chat_turn, get_chat_history_turns


def load_dotenv():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


load_dotenv()

GATE_SYSTEM_PROMPT = """You are "GATE ECE Mentor AI", an elite GATE Electronics & Communication Engineering (ECE) coach and tutor for GATE 2027.

Teaching & Problem Solving Framework:
When answering technical doubts or questions, structure your explanation pedagogically:
1. 💡 Concept & Core Intuition: What it represents physically in electronic circuits/systems.
2. 📐 Governing Formula & Derivation: Exact mathematical equations using standard ECE symbols.
3. ⚡ GATE Shortcut / Pro-Tip: Fast solving tricks to eliminate options or solve in under 90 seconds.
4. ⚠️ Common Mistake: Typical traps (sign conventions, radian vs Hz, dependent sources, active vs passive).
5. 🎯 Quick Check: 1 high-yield practice checkpoint.

CRITICAL TELEGRAM FORMATTING RULES:
- NEVER use LaTeX math delimiters ($ or $$ or \\( or \\)). Telegram DOES NOT render LaTeX!
- NEVER write LaTeX commands like \\text{}, \\frac{}, \\mathbf{}, \\cdot.
- ALWAYS use clean Unicode characters and standard engineering notation:
  • Ohm symbol: Ω (e.g. 50 Ω, 1 kΩ, 2.2 MΩ)
  • Micro prefix: µ (e.g. 10 µF, 5 µs, 100 µA)
  • Voltage & Current: V, mV, kV, A, mA, µA, I, V
  • Greek symbols: π, ω, τ, α, β, γ, θ, λ, σ, η, ε, μ, Δ
  • Mathematical operators: ×, ÷, ±, ≤, ≥, ≠, ≈, √, ∞, →, ⟹
  • Superscripts & Subscripts: ², ³, ⁿ, ⁰, ¹, ₀, ₁, ₂, ₃, ᵢ, ₙ, ₚ (e.g., f₀, ω₀, L₁, L₂, v₁, v₂, nᵢ², kT/q)
  • Fractions: write as a/b or (a + b)/c (e.g., 5/18, 1/(2πRC), ω₀/(2π))
- Use only valid Telegram HTML tags: <b>bold</b>, <i>italic</i>, <code>code</code>.
- Branch: Strictly GATE ECE (Networks, EDC, Analog, Digital, Control, Communications, EMFT, Math, Aptitude).
"""

USER_REQUEST_TIMESTAMPS = {}


def check_rate_limit(chat_id, max_per_min=12):
    if not chat_id:
        return True
    now = time.time()
    ts_list = USER_REQUEST_TIMESTAMPS.setdefault(str(chat_id), [])
    ts_list = [t for t in ts_list if now - t < 60]
    USER_REQUEST_TIMESTAMPS[str(chat_id)] = ts_list
    if len(ts_list) >= max_per_min:
        return False
    ts_list.append(now)
    return True


def get_ai_credentials():
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    return gemini_key, groq_key


def add_chat_history(chat_id, role, text):
    if not chat_id:
        return
    try:
        add_chat_turn(str(chat_id), role, text)
    except Exception:
        pass


def get_chat_history(chat_id):
    if not chat_id:
        return []
    try:
        turns = get_chat_history_turns(str(chat_id), limit=8)
        return [{"role": t["role"], "text": t["parts"][0]["text"]} for t in turns]
    except Exception:
        return []


def clean_response_for_telegram(text):
    if not text:
        return ""

    # 1. Standard markdown headers & bold
    text = re.sub(r"^#{1,6}\s*(.*)", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    # 2. LaTeX formatting wrappers (run multiple times for nesting)
    for _ in range(3):
        text = re.sub(r"\\mathbf\{([^}]*)\}", r"<b>\1</b>", text)
        text = re.sub(r"\\mathit\{([^}]*)\}", r"<i>\1</i>", text)
        text = re.sub(r"\\(?:text|mathrm|textrm)\{([^}]*)\}", r"\1", text)
        text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1/\2)", text)
        text = re.sub(r"\\sqrt\{([^}]*)\}", r"√(\1)", text)

    # 3. LaTeX macros & symbols replacement
    replacements = [
        (r"\\Omega\b|\\Omega(?=[A-Z])", "Ω"),
        (r"\\ohm\b", "Ω"),
        (r"\\mu\b|\\mu(?=[A-Z\s])", "µ"),
        (r"\\pi\b", "π"),
        (r"\\tau\b", "τ"),
        (r"\\omega_0\b", "ω₀"),
        (r"\\omega\b", "ω"),
        (r"\\alpha\b", "α"),
        (r"\\beta\b", "β"),
        (r"\\gamma\b", "γ"),
        (r"\\theta\b", "θ"),
        (r"\\lambda\b", "λ"),
        (r"\\sigma\b", "σ"),
        (r"\\Delta\b", "Δ"),
        (r"\\delta\b", "δ"),
        (r"\\epsilon\b", "ε"),
        (r"\\eta\b", "η"),
        (r"\\approx\b", "≈"),
        (r"\\leq?\b", "≤"),
        (r"\\geq?\b", "≥"),
        (r"\\neq?\b", "≠"),
        (r"\\pm\b", "±"),
        (r"\\mp\b", "∓"),
        (r"\\times\b", "×"),
        (r"\\cdot\b", "·"),
        (r"\\rightarrow\b", "→"),
        (r"\\to\b", "→"),
        (r"\\implies\b", "⟹"),
        (r"\\degree\b", "°"),
        (r"\\circ\b", "°"),
        (r"\\infty\b", "∞"),
        (r"\\left\(", "("),
        (r"\\right\)", ")"),
        (r"\\left\[", "["),
        (r"\\right\]", "]"),
        (r"\\[,;!]", " "),
    ]
    for pattern, rep in replacements:
        text = re.sub(pattern, rep, text)

    # 4. Clean up remaining braces in sub/superscripts
    text = re.sub(r"_\{([a-zA-Z0-9_+ -]+)\}", r"_\1", text)
    text = re.sub(r"\^\{([a-zA-Z0-9_+ -]+)\}", r"^\1", text)

    # 5. Common single-character sub/superscripts
    sub_map = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "i": "ᵢ", "n": "ₙ", "p": "ₚ"}
    for k, v in sub_map.items():
        text = re.sub(rf"_{k}(?![a-zA-Z0-9])", v, text)

    sup_map = {"2": "²", "3": "³", "n": "ⁿ", "0": "⁰", "1": "¹"}
    for k, v in sup_map.items():
        text = re.sub(rf"\^{k}(?![a-zA-Z0-9])", v, text)
    text = re.sub(r"\^-1(?![0-9])", "⁻¹", text)

    # 6. Remove remaining LaTeX math fences ($$ and $)
    text = re.sub(r"\$\$", "", text)
    text = re.sub(r"\$", "", text)

    # 7. Clean code tags
    text = re.sub(r"```[a-z]*\n?(.*?)```", r"<code>\1</code>", text, flags=re.DOTALL)
    text = re.sub(r"`(.*?)`", r"<code>\1</code>", text)
    return text.strip()


def call_gemini(prompt, api_key, history=None, context_info=None):
    """
    Calls Google Gemini REST API using verified stable production models.
    """
    candidate_models = [
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-pro-latest",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash"
    ]
    last_err = None

    sys_text = GATE_SYSTEM_PROMPT
    if context_info:
        sys_text += f"\n\nActive Student Context: {context_info}"

    contents = []
    if history:
        for turn in history:
            r = "user" if turn.get("role") == "user" else "model"
            contents.append({
                "role": r,
                "parts": [{"text": turn.get("text", "")}]
            })
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })

    for model in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {
                "parts": [{"text": sys_text}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2048
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        full_text = "".join(p.get("text", "") for p in parts if p.get("text"))
                        if full_text:
                            return full_text
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (400, 404, 429, 503):
                continue
            raise e
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise last_err
    return "Could not generate response from Gemini."


def call_gemini_vision(prompt, image_bytes, api_key, mime_type="image/jpeg"):
    candidate_models = [
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-pro-latest",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash"
    ]
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    last_err = None

    user_prompt = (
        "You are an expert GATE Electronics & Communication Engineering (ECE) Mentor.\n"
        "A student has uploaded an image containing a circuit schematic, signal waveform, or GATE question.\n"
        "Structured Reasoning Framework:\n"
        "1. Circuit Interpretation: Identify all components, known values, sources, and node labels.\n"
        "2. Engineering Assumptions: State clearly (e.g., ideal op-amp in negative feedback, LTI, steady-state).\n"
        "3. Governing Equations: Formulate exact KCL/KVL, nodal, or transfer function expressions.\n"
        "4. Step-by-Step Calculation: Perform derivation with explicit steps.\n"
        "5. Final Answer: Highlight with units and sign conventions clearly.\n\n"
        "Student's Query: " + (prompt if prompt else "Analyze and solve this problem step-by-step.")
    )

    contents = [
        {
            "role": "user",
            "parts": [
                {"text": user_prompt},
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": b64_img
                    }
                }
            ]
        }
    ]

    for model in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        full_text = "".join(p.get("text", "") for p in parts if p.get("text"))
                        if full_text:
                            return full_text
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (400, 404, 429, 503):
                continue
            raise e
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise last_err
    return "Could not analyze the image."


def generate_gate_ai_vision_reply(prompt, image_bytes, chat_id=None, mime_type="image/jpeg"):
    if chat_id and not check_rate_limit(chat_id):
        return "⏳ <b>Please Slow Down:</b> You've sent several queries in rapid succession. Please wait 15 seconds!"

    gemini_key, _ = get_ai_credentials()
    if not gemini_key:
        return "⚠️ <i>Gemini API key is not configured in environment variables (GEMINI_API_KEY).</i>"

    try:
        raw_answer = call_gemini_vision(prompt, image_bytes, gemini_key, mime_type=mime_type)
        clean_ans = clean_response_for_telegram(raw_answer)
        if chat_id:
            add_chat_history(chat_id, "user", f"[Attached Circuit/Photo] {prompt}")
            add_chat_history(chat_id, "model", clean_ans)
        return clean_ans
    except Exception as e:
        print(f"[Vision Error] {e}")
        return "⚠️ <b>Vision Analysis Notice:</b> I couldn't clearly parse this circuit schematic right now. Please ensure the circuit diagram and component values are clearly lit and legible."


def generate_gate_ai_reply(query, chat_id=None, context_info=None):
    if chat_id and not check_rate_limit(chat_id):
        return "⏳ <b>Please Slow Down:</b> You've sent several questions in rapid succession. Please wait 15 seconds to protect your quota!"

    gemini_key, groq_key = get_ai_credentials()
    history = get_chat_history(chat_id) if chat_id else None

    if gemini_key:
        try:
            raw_answer = call_gemini(query, gemini_key, history=history, context_info=context_info)
            clean_ans = clean_response_for_telegram(raw_answer)
            if chat_id:
                add_chat_history(chat_id, "user", query)
                add_chat_history(chat_id, "model", clean_ans)
            return clean_ans
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"[Gemini HTTP {e.code}] {err_body[:200]}")
            if "leaked" in err_body.lower() or e.code == 403:
                return """⚠️ <b>Google Gemini Key Blocked:</b>\n━━━━━━━━━━━━━━━━━━━━━\nYour API key was revoked by Google security.\n\n👉 <b>How to fix in 30 seconds:</b>\n1. Visit: <b>https://aistudio.google.com/app/apikey</b>\n2. Generate a fresh API key.\n3. Update <code>GEMINI_API_KEY</code> in Render Environment Variables (or local <code>.env</code> file)."""
            elif e.code == 429:
                return "⏳ <b>Rate Limit Reached:</b> Gemini free tier limit reached. Please wait 10 seconds and ask again!"
            return "⚠️ <b>AI Mentor Temporarily Unavailable:</b> Google Gemini returned a service error. Please try again in 15 seconds."
        except Exception as e:
            print(f"[Gemini Connection Error] {e}")
            return "⚠️ <b>Connection Notice:</b> Could not establish connection to the AI mentor. Please try again shortly."

    # Fallback to local syllabus intelligence
    return generate_syllabus_fallback(query)


def search_local_syllabus(query):
    query_lower = query.lower()
    if not SYLLABUS_FILE.exists():
        return None
    try:
        with open(SYLLABUS_FILE, "r", encoding="utf-8") as f:
            syllabus = json.load(f)
    except Exception:
        return None

    matches = []
    for subject in syllabus.get("subjects", []):
        for module in subject.get("modules", []):
            score = 0
            if module.get("id", "").lower() in query_lower:
                score += 10
            for w in module.get("title", "").lower().split():
                if len(w) > 3 and w in query_lower:
                    score += 3
            for kc in module.get("key_concepts", []):
                for kw in str(kc).lower().split():
                    if len(kw) > 3 and kw in query_lower:
                        score += 3
            for fm in module.get("formulas", []):
                for fw in str(fm).lower().split():
                    if len(fw) > 3 and fw in query_lower:
                        score += 2
            if score > 0:
                matches.append((score, subject, module))

    matches.sort(key=lambda x: x[0], reverse=True)
    if matches:
        _, best_subj, best_mod = matches[0]
        return best_subj, best_mod
    return None


def generate_syllabus_fallback(query):
    result = search_local_syllabus(query)
    if result:
        subj, mod = result
        kc_list = "\n".join([f"• {c}" for c in mod.get("key_concepts", [])])
        return f"""📚 <b>GATE ECE Topic Reference: [{mod.get('id')}] {mod.get('title')}</b>\n━━━━━━━━━━━━━━━━━━━━━\n📖 <b>Subject:</b> {subj.get('name')}\n\n💡 <b>Key Concepts:</b>\n{kc_list}"""
    return "💬 <i>I am processing your doubt. Please send your query again or use <code>/today</code> or <code>/pyq</code>.</i>"


LOCAL_QUIZ_BANK = [
    {
        "subject_code": "NET",
        "module_id": "NET-M01",
        "topic_name": "Series RLC Resonance",
        "question": "In a series RLC circuit at resonance, what is the net impedance Z seen across the source?",
        "options": ["Z = R (Purely Resistive)", "Z = 0 (Short Circuit)", "Z = ∞ (Open Circuit)", "Z = j(ωL - 1/ωC)"],
        "correct_option_id": 0,
        "explanation": "At resonance ωL = 1/ωC, reactive parts cancel out completely. Impedance is minimum: Z = R."
    },
    {
        "subject_code": "EDC",
        "module_id": "EDC-M02",
        "topic_name": "P-N Junction Built-in Potential",
        "question": "In an abrupt silicon P-N junction at 300 K, if the acceptor doping Na is doubled while Nd remains constant, the built-in potential Vbi will:",
        "options": ["Double", "Remain unchanged", "Increase by VT * ln(2) (~18 mV)", "Decrease by half"],
        "correct_option_id": 2,
        "explanation": "Vbi = VT * ln(Na*Nd / ni^2). Doubling Na adds VT * ln(2) ≈ 18 mV (logarithmic increase)."
    },
    {
        "subject_code": "ANALOG",
        "module_id": "ANA-M03",
        "topic_name": "Op-Amp Virtual Short Concept",
        "question": "An ideal operational amplifier with negative feedback has an open-loop gain A -> ∞. The differential input voltage Vid is:",
        "options": ["Equal to output voltage Vout", "Infinitely large", "Virtually zero (Virtual Short)", "Equal to supply Vcc"],
        "correct_option_id": 2,
        "explanation": "Because Vout is finite and A -> ∞, Vid = Vout/A -> 0 (Virtual Short concept)."
    },
    {
        "subject_code": "CONTROL",
        "module_id": "CTRL-M01",
        "topic_name": "LTI System Stability",
        "question": "For a stable continuous-time LTI system, all poles of the transfer function H(s) must lie:",
        "options": ["On the imaginary jω axis", "In the strict Left Half of the s-plane", "Inside the unit circle on z-plane", "Anywhere except the origin"],
        "correct_option_id": 1,
        "explanation": "Continuous-time BIBO stability requires the ROC to include the jω axis, meaning all poles must have Re(s) < 0."
    },
    {
        "subject_code": "COMM",
        "module_id": "COMM-M02",
        "topic_name": "Uniform PCM Quantization SQNR",
        "question": "In PCM (Pulse Code Modulation), if the number of quantization bits per sample increases from n to n+1, SQNR increases by:",
        "options": ["3 dB", "6 dB", "12 dB", "1.76 dB"],
        "correct_option_id": 1,
        "explanation": "SQNR in PCM is SQNR ≈ 1.76 + 6.02*n dB. Adding 1 bit increases SQNR by ~6 dB."
    }
]


def generate_native_quiz_poll(active_subject_name="Networks, Signals & Systems", active_subject_code="NET", active_module_id="NET-M01", allowed_topics=None):
    gemini_key, _ = get_ai_credentials()
    topics_prompt = f"The 'topic_name' must be chosen strictly from this module's topics: {allowed_topics}" if allowed_topics else ""

    if gemini_key:
        prompt = (
            f"Generate a challenging, authentic 2-mark GATE ECE MCQ for the subject '{active_subject_name}' ({active_subject_code}) under module {active_module_id}.\n"
            f"{topics_prompt}\n"
            "Output strictly valid JSON with no markdown, exactly matching this schema:\n"
            "{\n"
            '  "topic_name": "Exact concept name",\n'
            '  "question": "Clear question text (max 250 chars)",\n'
            '  "options": ["Option 0", "Option 1", "Option 2", "Option 3"],\n'
            '  "correct_option_id": 0,\n'
            '  "explanation": "Precise mathematical reason (max 180 chars)"\n'
            "}\n"
            "Note: correct_option_id must be an integer between 0 and 3."
        )
        try:
            raw = call_gemini(prompt, gemini_key)
            cleaned = re.sub(r"^```[a-z]*\s*", "", raw.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE)
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                quiz_data = json.loads(cleaned[start:end+1])
                opts = quiz_data.get("options", [])
                cid = quiz_data.get("correct_option_id")
                if len(opts) == 4 and isinstance(cid, int) and 0 <= cid <= 3:
                    quiz_data["module_id"] = active_module_id
                    quiz_data["subject_code"] = active_subject_code
                    if "topic_name" not in quiz_data or not quiz_data["topic_name"]:
                        quiz_data["topic_name"] = allowed_topics[0] if allowed_topics else f"{active_subject_code} Conceptual"
                    return quiz_data
        except Exception as e:
            print(f"[Quiz Gen Notice] {e}")

    # Fallback to local bank matching subject
    matches = [q for q in LOCAL_QUIZ_BANK if q["subject_code"] == active_subject_code]
    pick = dict(matches[0] if matches else random.choice(LOCAL_QUIZ_BANK))
    return pick


def generate_practice_question(active_subject_name="Networks, Signals & Systems", active_subject_code="NET", active_module_id="NET-M01", allowed_topics=None, chat_id=None):
    """
    Generates a structured AI practice question with deterministic options and explanation.
    """
    if chat_id and not check_rate_limit(chat_id):
        return None, "⏳ Rate limit: Please wait 15 seconds before generating another practice question."

    gemini_key, _ = get_ai_credentials()
    topics_prompt = f"The 'topic_name' must be chosen strictly from: {allowed_topics}" if allowed_topics else ""

    if gemini_key:
        prompt = (
            f"Generate a rigorous 2-mark GATE ECE practice problem for '{active_subject_name}' ({active_subject_code}).\n"
            f"{topics_prompt}\n"
            "Output strictly valid JSON with no markdown:\n"
            "{\n"
            '  "topic_name": "Specific concept name",\n'
            '  "question": "Full problem statement with circuit/parameter details",\n'
            '  "options": ["Option A", "Option B", "Option C", "Option D"],\n'
            '  "correct_option_id": 0,\n'
            '  "explanation": "Detailed step-by-step mathematical derivation"\n'
            "}\n"
            "Note: correct_option_id must be an integer between 0 and 3."
        )
        try:
            raw = call_gemini(prompt, gemini_key)
            cleaned = re.sub(r"^```[a-z]*\s*", "", raw.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE)
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(cleaned[start:end+1])
                opts = data.get("options", [])
                cid = data.get("correct_option_id")
                if len(opts) == 4 and isinstance(cid, int) and 0 <= cid <= 3:
                    data["module_id"] = active_module_id
                    data["subject_code"] = active_subject_code
                    if "topic_name" not in data or not data["topic_name"]:
                        data["topic_name"] = allowed_topics[0] if allowed_topics else f"{active_subject_code} Concept"
                    return data, None
        except Exception as e:
            print(f"[Practice Gen Error] {e}")

    # Fallback
    matches = [q for q in LOCAL_QUIZ_BANK if q["subject_code"] == active_subject_code]
    pick = dict(matches[0] if matches else random.choice(LOCAL_QUIZ_BANK))
    return pick, None


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_config():
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)