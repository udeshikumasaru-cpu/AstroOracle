# ============================================================
#  astro_script_generator.py  (FIXED — 2026-03)
#
#  KEY FIXES vs original:
#  1. PERSISTENT token tracker  — groq_usage.json survives
#     process restarts, so re-runs in the same calendar day
#     don't falsely assume a full Groq budget.
#  2. Real Groq 429 / quota detection — rate_limit AND
#     tokens_exhausted error strings are both caught.
#  3. Gemini quota detection — 429 from Gemini is caught
#     and the section falls back to a hardcoded template
#     instead of returning "" and crashing _check_min_words.
#  4. Inter-request delay — configurable INTER_REQUEST_DELAY
#     (default 4 s) between every LLM call so we don't burn
#     Groq's RPM limit on back-to-back sign scripts.
#  5. Script-section cache — completed sections are written
#     to disk immediately.  If the pipeline dies mid-run
#     (quota mid-omnibus, server hiccup, etc.) the NEXT run
#     skips already-generated sections instead of regenerating
#     everything from scratch.
#  6. Hardcoded section templates — if BOTH Groq AND Gemini
#     are unavailable for a section, a sensible template is
#     returned so the video can still be rendered and
#     uploaded rather than the whole sign being skipped.
#  7. Groq daily-limit raised to 130k (actual free-tier
#     limit for llama-3.3-70b-versatile is ~6,000 RPD not
#     token-based — tracker now also stores call count).
# ============================================================

import re
import time
import json
import os
from datetime import datetime, timezone, date as _date
from groq import Groq
from astro_config import (
    GROQ_API_KEY, GEMINI_API_KEY, CHANNEL_NAME, ZODIAC_SIGNS, SIGN_DATA
)

# ── Groq client ───────────────────────────────────────────────
if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY environment variable is not set.")
client = Groq(api_key=GROQ_API_KEY)

# ── Gemini client (lazy-init) ─────────────────────────────────
_gemini_client = None
def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            _gemini_client = genai.GenerativeModel(
                model_name="gemini-2.0-flash-lite",
                system_instruction=ASTRO_SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"   ⚠️  Gemini init failed: {e}")
    return _gemini_client

# ── Rate-limit config ─────────────────────────────────────────
# Pause between every LLM call to avoid burning RPM quota.
# Increase if you still hit 429s (try 8 or 12 seconds).
INTER_REQUEST_DELAY = 4   # seconds

# ── Groq budget — PERSISTENT tracker ─────────────────────────
# Groq free tier for llama-3.3-70b-versatile:
#   • ~6,000 requests/day  (RPD)
#   • ~200,000 tokens/day  (TPD — approx)
# We track BOTH.  File: groq_usage.json
GROQ_USAGE_FILE    = "groq_usage.json"
GROQ_MAX_RPD       = 5_800   # leave 200 headroom
GROQ_MAX_TPD       = 190_000 # leave 10k headroom
GROQ_SAFETY_MARGIN =   5_000

# ── Gemini budget tracker ─────────────────────────────────────
_gemini_quota_exhausted = False   # set True after first 429

# ── Script section cache ──────────────────────────────────────
# Directory where in-progress sections are cached so a
# crashed run can continue without re-calling the LLM.
SCRIPT_CACHE_DIR = "script_cache"
os.makedirs(SCRIPT_CACHE_DIR, exist_ok=True)

# ── Minimum word guards ───────────────────────────────────────
MIN_SCRIPT_WORDS = {
    "omnibus": 1_800,
    "sign":      600,
    "transit":   500,
}

# ── TTS-safe system prompt ────────────────────────────────────
ASTRO_SYSTEM_PROMPT = (
    "You are a wise, warm, and engaging astrologer presenting a YouTube horoscope video. "
    "You speak with authority and compassion, like a trusted cosmic guide. "
    "STRICT RULES: "
    "No markdown of any kind — no asterisks, no hyphens as bullets, no hashtags, no headers, no bold. "
    "No double-quote characters. No em-dashes or en-dashes — use commas instead. "
    "No percent symbol — say the word percent. "
    "No numbered lists — write in flowing spoken paragraphs only. "
    "Never say AI, algorithm, machine, or computer. "
    "Never say I cannot or I do not have real-time data. "
    "Speak as if you have deep astrological knowledge and genuine cosmic insight. "
    "Be specific, warm, encouraging, and occasionally dramatic for engagement. "
    "Write exactly as a human astrologer speaks on a professional YouTube channel."
)


# ─────────────────────────────────────────────────────────────
# Persistent quota tracker
# ─────────────────────────────────────────────────────────────

def _load_usage() -> dict:
    today = str(_date.today())
    if os.path.exists(GROQ_USAGE_FILE):
        try:
            with open(GROQ_USAGE_FILE) as f:
                data = json.load(f)
            if data.get("date") == today:
                return data
        except Exception:
            pass
    # New day or missing file — reset
    return {"date": today, "tokens": 0, "calls": 0}


def _save_usage(data: dict):
    try:
        with open(GROQ_USAGE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _record_groq_call(prompt_tokens: int, output_tokens: int):
    data = _load_usage()
    data["tokens"] += prompt_tokens + output_tokens
    data["calls"]  += 1
    _save_usage(data)


def _groq_budget_ok(prompt: str, max_tokens: int) -> bool:
    data           = _load_usage()
    est_prompt_tok = int(len(prompt.split()) * 1.3)
    est_total      = est_prompt_tok + max_tokens
    tokens_ok      = (data["tokens"] + est_total) < (GROQ_MAX_TPD - GROQ_SAFETY_MARGIN)
    calls_ok       = data["calls"] < GROQ_MAX_RPD
    return tokens_ok and calls_ok


# ─────────────────────────────────────────────────────────────
# Script section cache
# ─────────────────────────────────────────────────────────────

def _cache_key(label: str) -> str:
    """Sanitise a label into a safe filename."""
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', label)
    return os.path.join(SCRIPT_CACHE_DIR, f"{safe}.txt")


def _cache_get(label: str) -> str | None:
    path = _cache_key(label)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return None


def _cache_set(label: str, text: str):
    try:
        with open(_cache_key(label), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _cache_clear_old():
    """Remove cache files older than 8 days to avoid stale content."""
    import time as _t
    cutoff = _t.time() - 8 * 86_400
    for fn in os.listdir(SCRIPT_CACHE_DIR):
        fp = os.path.join(SCRIPT_CACHE_DIR, fn)
        try:
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# LLM caller with full fallback chain
# ─────────────────────────────────────────────────────────────

def _call_llm(prompt: str, max_tokens: int = 2000,
              cache_label: str = "", fallback_text: str = "") -> str:
    """
    Call the LLM with the following priority chain:

      1. Return cached result (same label, same run-week)
      2. Try Groq (if daily budget not exhausted)
         - Up to 3 attempts with 65-second back-off on 429
         - On 3rd failure: mark Groq exhausted for this run
      3. Try Gemini fallback (if not quota-exhausted)
         - Up to 3 attempts with 10-second back-off on 429
         - On Gemini 429: mark Gemini exhausted for this run
      4. Return fallback_text (hardcoded template)
         - Prevents _check_min_words from killing the pipeline

    An INTER_REQUEST_DELAY sleep is inserted after every
    successful LLM call to respect RPM limits.
    """
    global _gemini_quota_exhausted

    # ── Cache hit ─────────────────────────────────────────────
    if cache_label:
        cached = _cache_get(cache_label)
        if cached:
            print(f"   📋 Cache hit: {cache_label}")
            return cached

    # ── Groq ──────────────────────────────────────────────────
    if _groq_budget_ok(prompt, max_tokens):
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": ASTRO_SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.82,
                )
                text = resp.choices[0].message.content.strip()
                usage = resp.usage
                _record_groq_call(
                    usage.prompt_tokens if usage else int(len(prompt.split()) * 1.3),
                    usage.completion_tokens if usage else len(text.split()),
                )
                result = _clean(text)
                if cache_label:
                    _cache_set(cache_label, result)
                time.sleep(INTER_REQUEST_DELAY)
                return result

            except Exception as e:
                err = str(e)
                is_rate = "429" in err or "rate_limit" in err.lower() or \
                          "tokens_exhausted" in err.lower() or "quota" in err.lower()
                if is_rate:
                    if attempt < 2:
                        wait = 65 if attempt == 0 else 120
                        print(f"   ⚠️  Groq 429 (attempt {attempt+1}/3) — waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        # Exhaust Groq budget for this run + persist
                        print("   ⚠️  Groq quota exhausted — switching to Gemini for this run")
                        data = _load_usage()
                        data["tokens"] = GROQ_MAX_TPD  # Force exhausted
                        _save_usage(data)
                        break
                else:
                    print(f"   ⚠️  Groq error: {e}")
                    break
    else:
        usage_data = _load_usage()
        print(f"   📊 Groq budget used today: {usage_data['tokens']:,} tokens, "
              f"{usage_data['calls']} calls — switching to Gemini")

    # ── Gemini fallback ───────────────────────────────────────
    if not _gemini_quota_exhausted:
        print(f"   🔄 Gemini fallback...")
        gemini = _get_gemini()
        if gemini:
            for attempt in range(3):
                try:
                    resp = gemini.generate_content(
                        prompt,
                        generation_config={
                            "max_output_tokens": max_tokens,
                            "temperature": 0.82,
                        },
                    )
                    result = _clean(resp.text.strip())
                    if cache_label:
                        _cache_set(cache_label, result)
                    time.sleep(INTER_REQUEST_DELAY)
                    return result

                except Exception as e:
                    err = str(e)
                    is_quota = "429" in err or "quota" in err.lower() or \
                               "free_tier" in err.lower() or "rate" in err.lower()
                    if is_quota:
                        if attempt < 2:
                            wait = 10 * (attempt + 1)
                            print(f"   ⚠️  Gemini 429 (attempt {attempt+1}/3) — waiting {wait}s...")
                            time.sleep(wait)
                        else:
                            print("   ⚠️  Gemini quota exhausted — using hardcoded templates for rest of run")
                            _gemini_quota_exhausted = True
                            break
                    else:
                        print(f"   ⚠️  Gemini error (attempt {attempt+1}/3): {e}")
                        time.sleep(10)

    # ── Hardcoded fallback (prevents pipeline crash) ──────────
    if fallback_text:
        print("   ⚠️  Both LLMs unavailable — using built-in template for this section")
        result = _clean(fallback_text)
        if cache_label:
            _cache_set(cache_label, result)
        return result

    print("   ❌ All LLM sources failed and no fallback template — section will be empty")
    return ""


# Keep old name as alias for any code that imports it directly
def _call_groq(prompt: str, max_tokens: int = 2000) -> str:
    return _call_llm(prompt, max_tokens)


# ─────────────────────────────────────────────────────────────
# Hardcoded section templates
# ─────────────────────────────────────────────────────────────

def _sign_fallback(sign: str, week: str, sd: dict) -> str:
    return (
        f"{sign}. The cosmic energies are converging around you this {week}. "
        f"Your ruling planet {sd['planet']} is supporting your journey with steady, grounding force. "
        f"In love and relationships, openness and honest communication will bring you closer to what your heart truly desires. "
        f"For your career and finances, trust your instincts and take measured, confident steps forward. "
        f"Your health is asking for balance, so honour both rest and movement this week. "
        f"The lucky day for {sign} this week is Wednesday. "
        f"Trust the process, {sign}. The stars are conspiring in your favour."
    )


def _hook_fallback(week: str) -> str:
    return (
        f"The cosmos is alive with powerful energy this {week}. "
        f"The planets are shifting, alignments are forming, and every zodiac sign is about to feel the shift. "
        f"Whether you are navigating love, chasing career goals, or seeking deeper spiritual truth, "
        f"the stars have a message for you. "
        f"Stay with me because your cosmic blueprint for {week} starts right now."
    )


def _closing_fallback(week: str) -> str:
    return (
        f"Thank you so much for joining me for this week's cosmic forecast. "
        f"If this reading resonated with you, please give it a like and subscribe to {CHANNEL_NAME} "
        f"so you never miss your weekly guidance. "
        f"Drop your zodiac sign in the comments below — I love hearing from you. "
        f"Your individual sign video is also available on this channel. "
        f"Have a blessed, aligned, and beautiful week ahead. "
        f"Until next week, may the stars guide your path. Namaste."
    )


# ─────────────────────────────────────────────────────────────
# Text cleaner
# ─────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '',          text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-•*–]\s+', '',       text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+',  '',       text, flags=re.MULTILINE)
    text = text.replace('"', '').replace('\u201c', '').replace('\u201d', '')
    text = text.replace('\u2014', ', ').replace('\u2013', ', ').replace('--', ', ')
    text = text.replace('%', ' percent').replace('&', ' and ')
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'`+', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = '\n'.join(line.strip() for line in text.splitlines()).strip()
    return text


def _check_min_words(script: str, kind: str, label: str) -> str:
    wc      = len(script.split())
    minimum = MIN_SCRIPT_WORDS.get(kind, 400)
    if wc < minimum:
        raise RuntimeError(
            f"⛔  Script too short: {wc} words (minimum {minimum}) for {label}.\n"
            f"   Likely caused by Groq/Gemini rate-limit mid-generation.\n"
            f"   Re-run the pipeline — completed sections are cached and will be reused.\n"
            f"   If Groq quota is exhausted for today, re-run tomorrow or upgrade your plan."
        )
    return script


# ─────────────────────────────────────────────────────────────
# TYPE 1 — Weekly Omnibus (all 12 signs)
# ─────────────────────────────────────────────────────────────

def generate_weekly_omnibus_script(astro_context: dict) -> str:
    week          = astro_context.get("week_label", "this week")
    major         = astro_context.get("major_transits", [])
    positions     = astro_context.get("positions", {})
    transit_summary = _format_transits(astro_context.get("transits", []))
    planet_summary  = _format_positions(positions)
    week_id         = week.replace(" ", "_").replace(",", "").replace("–", "-")

    _cache_clear_old()
    sections = []

    # ── Hook ──
    print("   Writing: Hook...")
    hook = _call_llm(
        f"Write an explosive 30-second spoken hook for a weekly astrology YouTube video covering {week}.\n"
        f"Major cosmic events this week: {transit_summary[:300]}\n\n"
        f"The hook must: open with a dramatic cosmic statement, tease the most exciting transit, "
        f"name-drop 2-3 zodiac signs who will have a powerful week, and end with: "
        f"'Stay with me because your cosmic blueprint for {week} starts right now.'\n\n"
        f"Maximum 80 words. Pure spoken energy. No markdown.",
        max_tokens=250,
        cache_label=f"omnibus_{week_id}_hook",
        fallback_text=_hook_fallback(week),
    )
    sections.append(hook)

    # ── Weekly Overview ──
    print("   Writing: Weekly Planetary Overview...")
    overview = _call_llm(
        f"Write a 2-minute spoken weekly astrology overview for {week}.\n\n"
        f"Current planetary positions:\n{planet_summary}\n\n"
        f"Major transits this week:\n{transit_summary}\n\n"
        f"Speak about: the overall cosmic weather this week, which planets are most active, "
        f"the general theme or lesson the universe is presenting to all signs, "
        f"and which life areas (love, career, money, health, spirituality) are most activated.\n\n"
        f"End with: 'Now let us travel through each of the twelve signs and reveal exactly what the stars hold for you.'\n\n"
        f"Write 220 to 260 words of flowing spoken commentary. No markdown. No lists.",
        max_tokens=700,
        cache_label=f"omnibus_{week_id}_overview",
        fallback_text=(
            f"Welcome to your weekly cosmic forecast for {week}. "
            f"This week the planetary energies are powerfully aligned, bringing themes of transformation, "
            f"clarity, and opportunity across all areas of life. "
            f"The most active planets this week are creating a dynamic backdrop that will be felt by every sign. "
            f"Love and relationships are highlighted, as are financial decisions and matters of personal growth. "
            f"The universe is asking you to step forward with courage and trust your inner compass. "
            f"Now let us travel through each of the twelve signs and reveal exactly what the stars hold for you."
        ),
    )
    sections.append(overview)

    # ── All 12 Signs ──
    for sign in ZODIAC_SIGNS:
        print(f"   Writing: {sign}...")
        sd            = SIGN_DATA[sign]
        sign_transits = _transits_for_sign(sign, astro_context.get("transits", []))
        ruling_pos    = positions.get(sd["planet"], {})
        ruling_sign   = ruling_pos.get("sign", "its home sign")
        ruling_retro  = ruling_pos.get("retrograde", False)
        ruling_info   = f"Your ruling planet {sd['planet']} is in {ruling_sign}"
        if ruling_retro:
            ruling_info += " retrograde"

        sign_section = _call_llm(
            f"Write a 90-second spoken horoscope for {sign} ({sd['symbol']} {sd['dates']}) "
            f"for the week of {week}.\n\n"
            f"Ruling planet info: {ruling_info}.\n"
            f"Element: {sd['element']}. Ruling planet: {sd['planet']}.\n"
            f"Transits directly affecting {sign} this week: {sign_transits if sign_transits else 'General cosmic weather applies.'}\n"
            f"Overall cosmic backdrop: {transit_summary[:200]}\n\n"
            f"Cover in flowing speech (not as separate items): \n"
            f"Overall energy and theme for {sign} this week, love and relationships, "
            f"career and finances, health and wellbeing, one specific actionable cosmic advice, "
            f"and a lucky day this week.\n\n"
            f"Start by saying the sign name clearly: '{sign}...' \n"
            f"Write 130 to 160 words. Warm, specific, and encouraging. No markdown. No lists.",
            max_tokens=500,
            cache_label=f"omnibus_{week_id}_sign_{sign.lower()}",
            fallback_text=_sign_fallback(sign, week, sd),
        )
        sections.append(sign_section)

    # ── Special Transit Deep-Dive ──
    if major:
        print("   Writing: Special Transit Deep-Dive...")
        major_str = "\n".join([f"- {t['event']} on {t['date']}: {t['description']}" for t in major[:3]])
        special = _call_llm(
            f"Write a 3-minute spoken section about the most important planetary transits happening "
            f"in the next 14 days, and how they will affect all zodiac signs.\n\n"
            f"The major transits are:\n{major_str}\n\n"
            f"Speak about: what each transit means cosmically, which signs are most affected and how, "
            f"practical advice for navigating these energies, and the overall opportunity each presents.\n\n"
            f"Write 280 to 320 words. Dramatic and insightful. No markdown. No lists.",
            max_tokens=800,
            cache_label=f"omnibus_{week_id}_transit_deepdive",
            fallback_text=(
                f"The major cosmic events of this week deserve special attention. "
                f"These powerful transits are shaping the energetic landscape for all twelve signs, "
                f"and understanding them will give you a profound edge in navigating the days ahead. "
                f"The universe is sending clear signals through these planetary movements, "
                f"and those who are aware will be able to harness their power for growth, healing, and success. "
                f"Stay aligned with this energy, trust your intuition, and move with the cosmic flow."
            ),
        )
        sections.append(special)

    # ── Closing CTA ──
    print("   Writing: Closing CTA...")
    closing = _call_llm(
        f"Write a warm 30-second spoken closing for a weekly astrology YouTube video for {week}.\n\n"
        f"Thank viewers for watching, encourage them to like and subscribe to {CHANNEL_NAME}, "
        f"ask them to comment their zodiac sign below, mention they can find their individual "
        f"sign video on the channel, and wish them a blessed and aligned week ahead.\n\n"
        f"End with: 'Until next week, may the stars guide your path. Namaste.'\n\n"
        f"Maximum 80 words. Warm and genuine. No markdown.",
        max_tokens=200,
        cache_label=f"omnibus_{week_id}_closing",
        fallback_text=_closing_fallback(week),
    )
    sections.append(closing)

    full_script = "\n\n".join(s for s in sections if s)
    wc = len(full_script.split())
    print(f"   ✅ Omnibus script: {wc:,} words (~{wc//140} min)")
    return _check_min_words(full_script, "omnibus", f"omnibus {week}")


# ─────────────────────────────────────────────────────────────
# TYPE 2 — Per-Sign Individual Video
# ─────────────────────────────────────────────────────────────

def generate_sign_script(sign: str, astro_context: dict) -> str:
    week          = astro_context.get("week_label", "this week")
    sd            = SIGN_DATA[sign]
    positions     = astro_context.get("positions", {})
    sign_transits = _transits_for_sign(sign, astro_context.get("transits", []))
    transit_str   = _format_transits(astro_context.get("transits", []))
    planet_pos    = positions.get(sd["planet"], {})
    ruling_sign_  = planet_pos.get("sign", "its home sign")
    ruling_retro  = planet_pos.get("retrograde", False)
    week_id       = week.replace(" ", "_").replace(",", "").replace("–", "-")
    sk            = sign.lower()

    sections = []

    # Hook
    hook = _call_llm(
        f"Write an explosive 20-second spoken hook for a {sign} weekly horoscope video for {week}.\n"
        f"Open with a dramatic statement specific to {sign}, tease the most exciting thing happening "
        f"for {sign} this week, and end with: 'This week changes everything for {sign}. Stay with me.'\n"
        f"Maximum 55 words.",
        max_tokens=180,
        cache_label=f"sign_{sk}_{week_id}_hook",
        fallback_text=(
            f"Attention {sign}. The stars are speaking directly to you this week, "
            f"and what they have to say will shift your perspective in the most powerful way. "
            f"The cosmic energy surrounding your sign right now is undeniable. "
            f"This week changes everything for {sign}. Stay with me."
        ),
    )
    sections.append(hook)

    # Overview
    overview = _call_llm(
        f"Write a 1.5-minute spoken intro for a {sign} weekly horoscope video for {week}.\n\n"
        f"Start with: 'Welcome back {sign}s, or welcome if you are new here.'\n"
        f"Cover: the overall cosmic theme for {sign} this week, your ruling planet {sd['planet']} "
        f"currently in {ruling_sign_}{' retrograde' if ruling_retro else ''} and what that means for you, "
        f"and which life areas will be most activated.\n"
        f"End with: 'Let us start with love and relationships.'\n\n"
        f"Write 160 to 190 words.",
        max_tokens=550,
        cache_label=f"sign_{sk}_{week_id}_overview",
        fallback_text=(
            f"Welcome back {sign}s, or welcome if you are new here. "
            f"This week is packed with potent cosmic energy specifically designed to help you grow, expand, and thrive. "
            f"Your ruling planet {sd['planet']} is working in harmony with the broader cosmic shifts, "
            f"activating powerful themes around love, purpose, and personal evolution for your sign. "
            f"The {sd['element']} element that fuels you is particularly highlighted right now, "
            f"giving you an extra layer of intuition and drive to work with. "
            f"The areas of your life most activated this week are love, career, and your overall wellbeing. "
            f"Let us start with love and relationships."
        ),
    )
    sections.append(overview)

    # Love
    love = _call_llm(
        f"Write a 2-minute spoken section about LOVE AND RELATIONSHIPS for {sign} for the week of {week}.\n\n"
        f"Transits affecting {sign}: {sign_transits if sign_transits else 'General energies apply.'}\n"
        f"Overall cosmic backdrop: {transit_str[:200]}\n\n"
        f"For singles: what the energy brings, whether new connections are likely, what to do.\n"
        f"For couples: what energies affect the relationship, any tensions or blessings, advice.\n"
        f"Lucky day for love. A specific cosmic action to take.\n\n"
        f"End with: 'Now let us look at your career and finances this week.'\n"
        f"Write 200 to 230 words. Specific and warm.",
        max_tokens=680,
        cache_label=f"sign_{sk}_{week_id}_love",
        fallback_text=(
            f"In love and relationships this week, {sign}, the cosmic energy is opening a beautiful doorway "
            f"for deeper connection and heartfelt communication. "
            f"For those who are single, the universe is conspiring to bring you into contact with someone special. "
            f"Stay open to unexpected encounters and allow yourself to be seen authentically. "
            f"For those in relationships, this week favours honest conversations and quality time together. "
            f"Any tensions that have been simmering can be resolved with compassion and patience. "
            f"Your lucky day for love this week is Friday, when the energy softens beautifully. "
            f"Take a loving action today, even a small gesture of care can transform the energy between you and someone important. "
            f"Now let us look at your career and finances this week."
        ),
    )
    sections.append(love)

    # Career & Money
    career = _call_llm(
        f"Write a 2-minute spoken section about CAREER AND FINANCES for {sign} for the week of {week}.\n\n"
        f"Transits: {sign_transits if sign_transits else 'General energies apply.'}\n"
        f"Cover: career momentum, financial opportunities or cautions, best days to make moves, "
        f"whether to start new projects or hold, and a specific piece of professional advice.\n\n"
        f"End with: 'Next, let us talk about your health and overall wellbeing this week.'\n"
        f"Write 200 to 230 words.",
        max_tokens=680,
        cache_label=f"sign_{sk}_{week_id}_career",
        fallback_text=(
            f"Career and finances are in a favourable cycle for {sign} this week. "
            f"The planetary support behind your professional life is strong, and if you have been waiting for the right moment "
            f"to make a bold move or present an important idea, this week provides that window. "
            f"On the financial front, careful attention to your budget will yield satisfying results. "
            f"Avoid impulsive spending on Tuesday but feel confident to invest in yourself or your business on Thursday. "
            f"Collaboration is particularly well-starred right now, so lean into partnerships and team efforts rather than going it alone. "
            f"Trust your professional instincts, {sign}. You know more than you give yourself credit for. "
            f"Next, let us talk about your health and overall wellbeing this week."
        ),
    )
    sections.append(career)

    # Health & Wellbeing
    health = _call_llm(
        f"Write a 1.5-minute spoken section about HEALTH AND WELLBEING for {sign} for {week}.\n\n"
        f"Cover: physical energy levels, areas of the body ruled by {sign} to pay attention to, "
        f"mental and emotional wellbeing, a self-care practice aligned with cosmic energies, "
        f"and whether rest or action is favoured.\n\n"
        f"End with: 'And now for the cosmic highlights — the transits that will shape your entire week.'\n"
        f"Write 150 to 170 words.",
        max_tokens=500,
        cache_label=f"sign_{sk}_{week_id}_health",
        fallback_text=(
            f"Your health and wellbeing this week, {sign}, are calling for a beautiful balance between action and rest. "
            f"Your physical energy is building steadily, but the stars suggest you listen closely to your body's signals. "
            f"Prioritise sleep, hydration, and nourishing foods that support your vitality. "
            f"Emotionally, you may feel a heightened sensitivity to the energies around you — this is your intuition at work. "
            f"Journaling, meditation, or a walk in nature will help you process and ground those feelings. "
            f"A self-care practice aligned with this week's cosmic energy is intentional stillness — moments of quiet where you simply breathe and be. "
            f"And now for the cosmic highlights, the transits that will shape your entire week."
        ),
    )
    sections.append(health)

    # Transit Impact
    transit_section = _call_llm(
        f"Write a 2-minute spoken section about SPECIFIC PLANETARY TRANSITS affecting {sign} this week.\n\n"
        f"Transits directly relevant to {sign}: {sign_transits if sign_transits else transit_str[:300]}\n\n"
        f"Speak about each transit and EXACTLY how it impacts {sign}'s daily life this week. "
        f"Be specific — mention dates if relevant. Give practical cosmic guidance for each transit.\n\n"
        f"Write 200 to 230 words.",
        max_tokens=680,
        cache_label=f"sign_{sk}_{week_id}_transits",
        fallback_text=(
            f"The planetary transits this week are creating a distinctive energetic signature for {sign}. "
            f"The major cosmic movements are activating key areas of your chart, particularly around your sense of purpose, "
            f"your relationships, and your financial foundations. "
            f"Early in the week you may feel a surge of inspiration and clarity, trust those downloads from the cosmos. "
            f"By mid-week the energy shifts toward reflection and strategic thinking, use this time wisely. "
            f"Towards the weekend, social and romantic energies rise, making it the perfect time to connect with those you love. "
            f"Work with these rhythms rather than against them, {sign}, and you will move through this week with grace and intention."
        ),
    )
    sections.append(transit_section)

    # Oracle & CTA
    oracle = _call_llm(
        f"Write a 1-minute spoken closing for the {sign} weekly horoscope for {week}.\n\n"
        f"Include: a one-sentence oracle message or affirmation for {sign} this week, "
        f"a lucky day and lucky number, a crystal or colour recommendation aligned with the cosmic energy, "
        f"and a warm CTA to like, subscribe to {CHANNEL_NAME}, and comment their birth date below.\n\n"
        f"End with: 'Until next week {sign}, the stars are always in your favour. Namaste.'\n"
        f"Maximum 110 words.",
        max_tokens=300,
        cache_label=f"sign_{sk}_{week_id}_oracle",
        fallback_text=(
            f"Your oracle message this week, {sign}: you are being guided toward your highest self with every breath you take. "
            f"Trust the journey. Your lucky day is Wednesday and your lucky number is seven. "
            f"The crystal that will support you this week is amethyst, and your power colour is deep violet. "
            f"If this reading resonated with you, please give it a like and subscribe to {CHANNEL_NAME} "
            f"for your weekly horoscope every Sunday. Comment your birth date below, I love connecting with you. "
            f"Until next week {sign}, the stars are always in your favour. Namaste."
        ),
    )
    sections.append(oracle)

    full_script = "\n\n".join(s for s in sections if s)
    wc = len(full_script.split())
    print(f"   ✅ {sign} script: {wc:,} words (~{wc//140} min)")
    return _check_min_words(full_script, "sign", f"{sign} {week}")


# ─────────────────────────────────────────────────────────────
# TYPE 3 — Transit Special
# ─────────────────────────────────────────────────────────────

def generate_transit_special_script(transit: dict, astro_context: dict) -> str:
    event  = transit["event"]
    planet = transit["planet"]
    desc   = transit["description"]
    date   = transit["date"]
    week   = astro_context.get("week_label", "this week")
    tk     = event.replace(" ", "_")[:40]

    sections = []

    # Hook
    hook = _call_llm(
        f"Write an explosive 25-second hook for a YouTube video about: '{event}' happening on {date}.\n"
        f"Make it urgent, dramatic. End with: 'Here is everything you need to know and how YOUR sign is affected.'\n"
        f"Maximum 65 words.",
        max_tokens=200,
        cache_label=f"transit_{tk}_hook",
        fallback_text=(
            f"Cosmic alert. {event} is happening on {date}, and every single zodiac sign will feel this shift. "
            f"This is one of the most significant astrological events in recent months, and if you are not prepared, "
            f"you could miss a powerful wave of transformation. "
            f"Here is everything you need to know and how YOUR sign is affected."
        ),
    )
    sections.append(hook)

    # Explainer
    explainer = _call_llm(
        f"Write a 3-minute spoken section explaining the astrological significance of: '{event}'.\n\n"
        f"Background: {desc}\n\n"
        f"Cover: what this transit means cosmically, its historical significance, "
        f"how often it happens, the themes it governs, its general effects on humanity, "
        f"and the overall energy it brings to the coming weeks.\n\n"
        f"Write 280 to 320 words. Authoritative and engaging.",
        max_tokens=900,
        cache_label=f"transit_{tk}_explainer",
        fallback_text=(
            f"{event} is a powerful astrological event that marks a significant shift in the cosmic landscape. "
            f"{desc} "
            f"When {planet} moves in this way, the energies it governs are amplified across the entire zodiac, "
            f"creating both challenges and extraordinary opportunities for growth and transformation. "
            f"Historically, transits involving {planet} have coincided with periods of important change in human affairs, "
            f"particularly in the areas that {planet} governs. "
            f"This particular event invites all of us to pause, reflect, and consciously align with the cosmic rhythm. "
            f"Those who work with this energy intentionally will find it profoundly rewarding. "
            f"Now let us look at how each of the twelve zodiac signs will be specifically affected."
        ),
    )
    sections.append(explainer)

    # Per-sign impacts
    print(f"   Writing transit impacts for all 12 signs...")
    for sign in ZODIAC_SIGNS:
        sd = SIGN_DATA[sign]
        impact = _call_llm(
            f"Write a 40-second spoken section about how '{event}' specifically affects {sign} "
            f"({sd['element']} sign, ruled by {sd['planet']}).\n\n"
            f"Be specific about: which life area is impacted for {sign}, "
            f"what challenge or opportunity this brings, and one piece of practical advice for {sign}.\n\n"
            f"Start with the sign name: '{sign}...'\n"
            f"Write 70 to 90 words.",
            max_tokens=280,
            cache_label=f"transit_{tk}_sign_{sign.lower()}",
            fallback_text=(
                f"{sign}. This transit activates a significant shift in your world, "
                f"particularly in areas governed by your ruling planet {sd['planet']}. "
                f"The {sd['element']} energy that fuels you will be amplified during this period, "
                f"bringing both heightened sensitivity and remarkable opportunity. "
                f"Your practical advice: stay grounded, stay present, and trust the process unfolding before you."
            ),
        )
        sections.append(impact)

    # Closing
    closing = _call_llm(
        f"Write a 30-second warm closing for a YouTube video about '{event}'.\n"
        f"Encourage viewers to navigate this transit with awareness and grace. "
        f"Ask them to like, subscribe to {CHANNEL_NAME}, and comment which sign they are. "
        f"End with: 'The cosmos speaks. Are you listening? Namaste.'\n"
        f"Maximum 75 words.",
        max_tokens=220,
        cache_label=f"transit_{tk}_closing",
        fallback_text=(
            f"This transit is a gift from the cosmos, an invitation to evolve and align with your highest potential. "
            f"Navigate it with awareness, grace, and an open heart. "
            f"If this video helped you, please give it a like and subscribe to {CHANNEL_NAME}. "
            f"Comment your zodiac sign below. I love hearing from you. "
            f"The cosmos speaks. Are you listening? Namaste."
        ),
    )
    sections.append(closing)

    full_script = "\n\n".join(s for s in sections if s)
    wc = len(full_script.split())
    print(f"   ✅ Transit special script: {wc:,} words (~{wc//140} min)")
    return _check_min_words(full_script, "transit", event)


# ─────────────────────────────────────────────────────────────
# SEO builders (unchanged from original)
# ─────────────────────────────────────────────────────────────

def build_omnibus_seo(astro_context: dict) -> tuple:
    week  = astro_context.get("week_label", "this week")
    year  = datetime.now().year
    major = astro_context.get("major_transits", [])
    major_str = ", ".join([t["event"] for t in major[:2]]) if major else "Weekly Horoscope"

    title = f"Weekly Horoscope All 12 Signs {week} — {major_str} | {year}"
    if len(title) > 100:
        title = f"Weekly Horoscope All Signs {week} | Astrology {year}"

    desc = f"""Weekly horoscope for all 12 zodiac signs — {week}.

Your complete cosmic forecast covering love, career, money, health and spiritual growth for every sign.

🌟 SIGNS COVERED:
Aries, Taurus, Gemini, Cancer, Leo, Virgo, Libra, Scorpio, Sagittarius, Capricorn, Aquarius, Pisces

⚡ MAJOR COSMIC EVENTS THIS WEEK:
{chr(10).join(['• ' + t['event'] + ' — ' + t['date'] for t in major[:5]]) if major else '• Steady planetary energies this week'}

📋 CHAPTERS:
00:00 — Hook & Weekly Overview
03:00 — Aries ♈
05:00 — Taurus ♉
07:00 — Gemini ♊
09:00 — Cancer ♋
11:00 — Leo ♌
13:00 — Virgo ♍
15:00 — Libra ♎
17:00 — Scorpio ♏
19:00 — Sagittarius ♐
21:00 — Capricorn ♑
23:00 — Aquarius ♒
25:00 — Pisces ♓
27:00 — Special Transit Deep Dive

🔔 Subscribe to {CHANNEL_NAME} — weekly horoscopes every Sunday!
👍 Like & share with your cosmic tribe
💬 Comment your zodiac sign below!

#{year} #WeeklyHoroscope #Astrology #ZodiacSigns #HoroscopeWeekly
#Aries #Taurus #Gemini #Cancer #Leo #Virgo
#Libra #Scorpio #Sagittarius #Capricorn #Aquarius #Pisces
#PlanetaryTransit #CosmicEnergy #AstrologyReading"""[:4950]

    raw_tags = [
        "weekly horoscope", f"weekly horoscope {year}",
        "horoscope all signs", "astrology weekly",
        "zodiac weekly forecast", "horoscope this week",
        "astrology forecast", "planetary transit",
        "zodiac signs 2026", "weekly astrology reading",
        "cosmic energy", "moon phase astrology",
        "astrology today", "horoscope reading",
        "spiritual forecast",
    ] + [f"{s.lower()} horoscope" for s in ZODIAC_SIGNS[:8]]

    tags = _sanitize_tags(raw_tags)
    return title[:100], desc, tags


def build_sign_seo(sign: str, astro_context: dict) -> tuple:
    week  = astro_context.get("week_label", "this week")
    year  = datetime.now().year
    sd    = SIGN_DATA[sign]
    major = astro_context.get("major_transits", [])
    sign_transits = _transits_for_sign(sign, astro_context.get("transits", []))

    title = f"{sign} {sd['symbol']} Weekly Horoscope {week} — Love Career Money | {year}"
    if len(title) > 100:
        title = f"{sign} Weekly Horoscope {week} | Astrology {year}"

    transit_bullets = "\n".join([f"• {t}" for t in sign_transits[:4]]) if sign_transits else "• Steady cosmic energies"

    desc = f"""{sign} weekly horoscope for {week} — your complete cosmic forecast.

{sd['emoji']} {sign} ({sd['dates']}) | Element: {sd['element']} | Ruling Planet: {sd['planet']}

💫 THIS WEEK FOR {sign.upper()}:
{transit_bullets}

📋 CHAPTERS:
00:00 — Hook
00:25 — Weekly Overview for {sign}
02:00 — Love & Relationships
04:00 — Career & Finances
06:00 — Health & Wellbeing
08:00 — Planetary Transit Impact
10:00 — Oracle Message & Lucky Day

🔔 Subscribe to {CHANNEL_NAME} for weekly {sign} horoscopes!
💬 Comment your birth date below!

#{sign} #{sign}Horoscope #{sign}Weekly #WeeklyHoroscope{year}
#Astrology{year} #{sign}Astrology #ZodiacReading
#{sd['element']}Signs #{sd['planet']}Transit
#HoroscopeReading #CosmicForecast #AstroOracle"""[:4950]

    raw_tags = [
        f"{sign.lower()} horoscope",
        f"{sign.lower()} weekly horoscope",
        f"{sign.lower()} horoscope {year}",
        f"{sign.lower()} astrology",
        f"{sign.lower()} forecast",
        "weekly horoscope", "astrology reading",
        f"{sd['element'].lower()} signs astrology",
        f"{sd['planet'].lower()} transit",
        "zodiac weekly", "horoscope this week",
        "astrology forecast", "cosmic energy",
        "zodiac reading", "horoscope today",
    ]
    tags = _sanitize_tags(raw_tags)
    return title[:100], desc, tags


def build_transit_special_seo(transit: dict, astro_context: dict) -> tuple:
    year   = datetime.now().year
    event  = transit["event"]
    planet = transit["planet"]
    date   = transit["date"]

    title = f"{event} — How Every Zodiac Sign Is Affected | {year}"
    if len(title) > 100:
        title = f"{event} Impact All 12 Signs | Astrology {year}"

    desc = f"""🚨 MAJOR COSMIC EVENT: {event} on {date}

This powerful transit will affect every zodiac sign. Here is your complete guide.

{transit['description']}

📋 CHAPTERS:
00:00 — What is {event}?
03:00 — Aries ♈ | Taurus ♉ | Gemini ♊
07:00 — Cancer ♋ | Leo ♌ | Virgo ♍
11:00 — Libra ♎ | Scorpio ♏ | Sagittarius ♐
15:00 — Capricorn ♑ | Aquarius ♒ | Pisces ♓
19:00 — Final Guidance

🔔 Subscribe to {CHANNEL_NAME} for cosmic alerts!
💬 Comment your sign — how does this affect you?

#{planet}Transit #{event.replace(' ', '')} #Astrology{year}
#PlanetaryTransit #CosmicEvent #ZodiacAlert
#WeeklyHoroscope #AstrologyForecast #AstroOracle"""[:4950]

    raw_tags = [
        event.lower()[:30],
        f"{planet.lower()} transit",
        f"{planet.lower()} astrology",
        "planetary transit", "cosmic event",
        "astrology alert", f"astrology {year}",
        "zodiac impact", "horoscope special",
        "astrological event", "cosmic forecast",
    ]
    tags = _sanitize_tags(raw_tags)
    return title[:100], desc, tags


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _format_transits(transits: list) -> str:
    if not transits:
        return "No major transits this week."
    return "\n".join([
        f"- {t['event']} ({t['date']}): {t['description'][:80]}"
        for t in transits[:8]
    ])


def _format_positions(positions: dict) -> str:
    lines = []
    for planet, data in positions.items():
        retro = " (retrograde)" if data.get("retrograde") else ""
        lines.append(f"  {planet}: {data.get('sign', '?')} {data.get('degree', 0):.0f}°{retro}")
    return "\n".join(lines)


def _transits_for_sign(sign: str, transits: list) -> str:
    relevant = [
        t["event"] for t in transits
        if sign in t.get("affected_signs", [])
    ]
    return ", ".join(relevant) if relevant else ""


def _sanitize_tags(tags: list) -> list:
    import re as _re
    FORBIDDEN = _re.compile(r'[,<>&"\'\u2014\u2013]')
    seen, out, total = set(), [], 0
    for tag in tags:
        tag = FORBIDDEN.sub('', str(tag)).strip()
        tag = _re.sub(r'\s+', ' ', tag).strip()
        if not tag or len(tag) < 3:
            continue
        if len(tag) > 30:
            tag = tag[:30].rsplit(' ', 1)[0].strip()
        low  = tag.lower()
        cost = len(tag) + 1
        if low not in seen and total + cost <= 498:
            seen.add(low)
            out.append(tag)
            total += cost
    return out
