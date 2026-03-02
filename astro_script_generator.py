# ============================================================
#  astro_script_generator.py
#  Generates two types of scripts:
#
#  TYPE 1 — WEEKLY OMNIBUS VIDEO (~15-20 min)
#    All 12 signs in one video. Best for SEO & watch time.
#    Structure:
#      Hook (30s) → Weekly Overview → [12 Signs × ~90s each]
#      → Special Transits → Closing CTA
#
#  TYPE 2 — PER-SIGN INDIVIDUAL VIDEO (~8-10 min)
#    One video per zodiac sign. 12 videos per week.
#    Each has its own title, thumbnail, tags.
#    Best for niche targeting & Shorts extraction.
#
#  TYPE 3 — TRANSIT SPECIAL VIDEO (~10 min)
#    Triggered automatically when a MAJOR transit occurs.
#    e.g. "Mercury Retrograde — What Every Sign Must Know"
# ============================================================

import re
import time
from datetime import datetime, timezone
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

# ── Token budget tracker ──────────────────────────────────────
# Groq free tier: 100,000 tokens/day for llama-3.3-70b-versatile.
# A full weekly run (omnibus + 12 signs + ~10 transits) uses ~130k+
# tokens — well over the limit. We track usage and switch to Gemini
# Flash automatically when Groq budget drops below GROQ_SAFETY_MARGIN.
GROQ_DAILY_LIMIT   = 100_000
GROQ_SAFETY_MARGIN =   5_000   # stop Groq at 95k, use Gemini for rest
_groq_tokens_used  = 0         # running total for this process

def _estimate_tokens(prompt: str, max_tokens: int) -> int:
    """Rough estimate: ~1.3 tokens/word for prompt + max_tokens for output."""
    return int(len(prompt.split()) * 1.3) + max_tokens

def _groq_budget_ok(prompt: str, max_tokens: int) -> bool:
    remaining = GROQ_DAILY_LIMIT - GROQ_SAFETY_MARGIN - _groq_tokens_used
    return _estimate_tokens(prompt, max_tokens) <= remaining

# ── Minimum word guards ───────────────────────────────────────
# If a script is below these limits, Groq/Gemini clearly failed
# mid-generation. We raise RuntimeError to abort render+upload
# so garbage videos are never published.
MIN_SCRIPT_WORDS = {
    "omnibus": 1_800,   # ~13 min — full run should be 2500+
    "sign":      600,   # ~4 min  — normal is ~1000
    "transit":   500,   # ~3.5 min — normal is ~1000
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


def _call_groq(prompt: str, max_tokens: int = 2000) -> str:
    """
    Call Groq with retry + automatic Gemini fallback.

    Flow:
      1. If Groq budget remaining  → try Groq (up to 3 attempts with backoff)
      2. If Groq budget exhausted  → use Gemini Flash
      3. If Groq returns 429       → wait 65s and retry; after 2 failed
                                     retries mark budget as exhausted and
                                     switch to Gemini for the rest of the run
      4. If both fail              → return "" (section will be empty)
    """
    global _groq_tokens_used

    use_groq = _groq_budget_ok(prompt, max_tokens)

    if use_groq:
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
                # Track tokens used (output word count is a good proxy)
                _groq_tokens_used += _estimate_tokens(prompt, len(text.split()))
                budget_left = GROQ_DAILY_LIMIT - GROQ_SAFETY_MARGIN - _groq_tokens_used
                if budget_left < 20_000:
                    print(f"   📊 Groq budget: {_groq_tokens_used:,} used, {budget_left:,} remaining")
                return _clean(text)
            except Exception as e:
                err = str(e)
                if "429" in err or "rate_limit" in err.lower():
                    if attempt < 2:
                        print(f"   ⚠️  Groq 429 (attempt {attempt+1}/3) — waiting 65s...")
                        time.sleep(65)
                    else:
                        # 3 retries exhausted — mark budget as gone, fall through to Gemini
                        print(f"   ⚠️  Groq 429 — budget exhausted, switching to Gemini for rest of run")
                        _groq_tokens_used = GROQ_DAILY_LIMIT  # force Gemini from now on
                        use_groq = False
                        break
                else:
                    print(f"   ⚠️  Groq error: {e}")
                    break

    # ── Gemini fallback ───────────────────────────────────────
    if not use_groq:
        print(f"   🔄 Gemini fallback (Groq tokens used: {_groq_tokens_used:,}/{GROQ_DAILY_LIMIT - GROQ_SAFETY_MARGIN:,})")
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
                    return _clean(resp.text.strip())
                except Exception as e:
                    print(f"   ⚠️  Gemini error (attempt {attempt+1}/3): {e}")
                    time.sleep(10)

        print("   ❌ Both Groq and Gemini failed — section will be empty")

    return ""


def _check_min_words(script: str, kind: str, label: str) -> str:
    """
    Raise RuntimeError if script is too short to be a real video.
    This stops the pipeline from rendering + uploading garbage videos
    that result from Groq/Gemini rate-limit failures mid-generation.
    """
    wc = len(script.split())
    minimum = MIN_SCRIPT_WORDS.get(kind, 400)
    if wc < minimum:
        raise RuntimeError(
            f"⛔  Script too short: {wc} words (minimum {minimum}) for {label}.\n"
            f"   Likely caused by Groq/Gemini rate-limit mid-generation.\n"
            f"   Render + upload ABORTED to prevent garbage video being published.\n"
            f"   Re-run tomorrow when Groq daily quota resets (or upgrade to Dev Tier)."
        )
    return script


def _clean(text: str) -> str:
    """Strip markdown and non-TTS characters."""
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


# ─────────────────────────────────────────────────────────────
# TYPE 1 — Weekly Omnibus (all 12 signs)
# ─────────────────────────────────────────────────────────────

def generate_weekly_omnibus_script(astro_context: dict) -> str:
    """
    Generate a full ~15-minute weekly horoscope script
    covering all 12 signs plus planetary transit highlights.
    """
    week   = astro_context.get("week_label", "this week")
    major  = astro_context.get("major_transits", [])
    positions = astro_context.get("positions", {})

    # Build transit summary string for prompts
    transit_summary = _format_transits(astro_context.get("transits", []))
    planet_summary  = _format_positions(positions)

    sections = []

    # ── Hook ──
    print("   Writing: Hook...")
    hook = _call_groq(
        f"Write an explosive 30-second spoken hook for a weekly astrology YouTube video covering {week}.\n"
        f"Major cosmic events this week: {transit_summary[:300]}\n\n"
        f"The hook must: open with a dramatic cosmic statement, tease the most exciting transit, "
        f"name-drop 2-3 zodiac signs who will have a powerful week, and end with: "
        f"'Stay with me because your cosmic blueprint for {week} starts right now.'\n\n"
        f"Maximum 80 words. Pure spoken energy. No markdown.", max_tokens=250
    )
    sections.append(hook)

    # ── Weekly Overview ──
    print("   Writing: Weekly Planetary Overview...")
    overview = _call_groq(
        f"Write a 2-minute spoken weekly astrology overview for {week}.\n\n"
        f"Current planetary positions:\n{planet_summary}\n\n"
        f"Major transits this week:\n{transit_summary}\n\n"
        f"Speak about: the overall cosmic weather this week, which planets are most active, "
        f"the general theme or lesson the universe is presenting to all signs, "
        f"and which life areas (love, career, money, health, spirituality) are most activated.\n\n"
        f"End with: 'Now let us travel through each of the twelve signs and reveal exactly what the stars hold for you.'\n\n"
        f"Write 220 to 260 words of flowing spoken commentary. No markdown. No lists.",
        max_tokens=700
    )
    sections.append(overview)

    # ── All 12 Signs ──
    for sign in ZODIAC_SIGNS:
        print(f"   Writing: {sign}...")
        sd           = SIGN_DATA[sign]
        sign_transits = _transits_for_sign(sign, astro_context.get("transits", []))
        ruling_pos    = positions.get(sd["planet"], {})
        ruling_sign   = ruling_pos.get("sign", "unknown")
        ruling_retro  = ruling_pos.get("retrograde", False)
        ruling_info   = f"Your ruling planet {sd['planet']} is in {ruling_sign}"
        if ruling_retro:
            ruling_info += " retrograde"

        sign_section = _call_groq(
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
            max_tokens=500
        )
        sections.append(sign_section)

    # ── Special Transit Deep-Dive ──
    if major:
        print("   Writing: Special Transit Deep-Dive...")
        major_str = "\n".join([f"- {t['event']} on {t['date']}: {t['description']}" for t in major[:3]])
        special = _call_groq(
            f"Write a 3-minute spoken section about the most important planetary transits happening "
            f"in the next 14 days, and how they will affect all zodiac signs.\n\n"
            f"The major transits are:\n{major_str}\n\n"
            f"Speak about: what each transit means cosmically, which signs are most affected and how, "
            f"practical advice for navigating these energies, and the overall opportunity each presents.\n\n"
            f"Write 280 to 320 words. Dramatic and insightful. No markdown. No lists.",
            max_tokens=800
        )
        sections.append(special)

    # ── Closing CTA ──
    print("   Writing: Closing CTA...")
    closing = _call_groq(
        f"Write a warm 30-second spoken closing for a weekly astrology YouTube video for {week}.\n\n"
        f"Thank viewers for watching, encourage them to like and subscribe to {CHANNEL_NAME}, "
        f"ask them to comment their zodiac sign below, mention they can find their individual "
        f"sign video on the channel, and wish them a blessed and aligned week ahead.\n\n"
        f"End with: 'Until next week, may the stars guide your path. Namaste.'\n\n"
        f"Maximum 80 words. Warm and genuine. No markdown.", max_tokens=200
    )
    sections.append(closing)

    full_script = "\n\n".join(s for s in sections if s)
    wc = len(full_script.split())
    print(f"   ✅ Omnibus script: {wc:,} words (~{wc//140} min)")
    return _check_min_words(full_script, "omnibus", f"omnibus {week}")


# ─────────────────────────────────────────────────────────────

def generate_sign_script(sign: str, astro_context: dict) -> str:
    """
    Generate a full ~8-minute individual horoscope script
    for a single zodiac sign.
    """
    week          = astro_context.get("week_label", "this week")
    sd            = SIGN_DATA[sign]
    positions     = astro_context.get("positions", {})
    sign_transits = _transits_for_sign(sign, astro_context.get("transits", []))
    transit_str   = _format_transits(astro_context.get("transits", []))
    planet_pos    = positions.get(sd["planet"], {})
    ruling_sign_  = planet_pos.get("sign", "")
    ruling_retro  = planet_pos.get("retrograde", False)

    sections = []

    # Hook
    hook = _call_groq(
        f"Write an explosive 20-second spoken hook for a {sign} weekly horoscope video for {week}.\n"
        f"Open with a dramatic statement specific to {sign}, tease the most exciting thing happening "
        f"for {sign} this week, and end with: 'This week changes everything for {sign}. Stay with me.'\n"
        f"Maximum 55 words.", max_tokens=180
    )
    sections.append(hook)

    # Overview
    overview = _call_groq(
        f"Write a 1.5-minute spoken intro for a {sign} weekly horoscope video for {week}.\n\n"
        f"Start with: 'Welcome back {sign}s, or welcome if you are new here.'\n"
        f"Cover: the overall cosmic theme for {sign} this week, your ruling planet {sd['planet']} "
        f"currently in {ruling_sign_}{' retrograde' if ruling_retro else ''} and what that means for you, "
        f"and which life areas will be most activated.\n"
        f"End with: 'Let us start with love and relationships.'\n\n"
        f"Write 160 to 190 words.", max_tokens=550
    )
    sections.append(overview)

    # Love
    love = _call_groq(
        f"Write a 2-minute spoken section about LOVE AND RELATIONSHIPS for {sign} for the week of {week}.\n\n"
        f"Transits affecting {sign}: {sign_transits if sign_transits else 'General energies apply.'}\n"
        f"Overall cosmic backdrop: {transit_str[:200]}\n\n"
        f"For singles: what the energy brings, whether new connections are likely, what to do.\n"
        f"For couples: what energies affect the relationship, any tensions or blessings, advice.\n"
        f"Lucky day for love. A specific cosmic action to take.\n\n"
        f"End with: 'Now let us look at your career and finances this week.'\n"
        f"Write 200 to 230 words. Specific and warm.", max_tokens=680
    )
    sections.append(love)

    # Career & Money
    career = _call_groq(
        f"Write a 2-minute spoken section about CAREER AND FINANCES for {sign} for the week of {week}.\n\n"
        f"Transits: {sign_transits if sign_transits else 'General energies apply.'}\n"
        f"Cover: career momentum, financial opportunities or cautions, best days to make moves, "
        f"whether to start new projects or hold, and a specific piece of professional advice.\n\n"
        f"End with: 'Next, let us talk about your health and overall wellbeing this week.'\n"
        f"Write 200 to 230 words.", max_tokens=680
    )
    sections.append(career)

    # Health & Wellbeing
    health = _call_groq(
        f"Write a 1.5-minute spoken section about HEALTH AND WELLBEING for {sign} for {week}.\n\n"
        f"Cover: physical energy levels, areas of the body ruled by {sign} to pay attention to, "
        f"mental and emotional wellbeing, a self-care practice aligned with cosmic energies, "
        f"and whether rest or action is favoured.\n\n"
        f"End with: 'And now for the cosmic highlights — the transits that will shape your entire week.'\n"
        f"Write 150 to 170 words.", max_tokens=500
    )
    sections.append(health)

    # Transit Impact
    transit_section = _call_groq(
        f"Write a 2-minute spoken section about SPECIFIC PLANETARY TRANSITS affecting {sign} this week.\n\n"
        f"Transits directly relevant to {sign}: {sign_transits if sign_transits else transit_str[:300]}\n\n"
        f"Speak about each transit and EXACTLY how it impacts {sign}'s daily life this week. "
        f"Be specific — mention dates if relevant. Give practical cosmic guidance for each transit.\n\n"
        f"Write 200 to 230 words.", max_tokens=680
    )
    sections.append(transit_section)

    # Weekly Oracle Message & CTA
    oracle = _call_groq(
        f"Write a 1-minute spoken closing for the {sign} weekly horoscope for {week}.\n\n"
        f"Include: a one-sentence oracle message or affirmation for {sign} this week, "
        f"a lucky day and lucky number, a crystal or colour recommendation aligned with the cosmic energy, "
        f"and a warm CTA to like, subscribe to {CHANNEL_NAME}, and comment their birth date below.\n\n"
        f"End with: 'Until next week {sign}, the stars are always in your favour. Namaste.'\n"
        f"Maximum 110 words.", max_tokens=300
    )
    sections.append(oracle)

    full_script = "\n\n".join(s for s in sections if s)
    wc = len(full_script.split())
    print(f"   ✅ {sign} script: {wc:,} words (~{wc//140} min)")
    return _check_min_words(full_script, "sign", f"{sign} {week}")
# ─────────────────────────────────────────────────────────────

def generate_transit_special_script(transit: dict, astro_context: dict) -> str:
    """
    Generate a focused ~10-minute video about a single major transit
    and its impact on all 12 signs.
    """
    event   = transit["event"]
    planet  = transit["planet"]
    desc    = transit["description"]
    date    = transit["date"]
    week    = astro_context.get("week_label", "this week")

    sections = []

    # Hook
    hook = _call_groq(
        f"Write an explosive 25-second hook for a YouTube video about: '{event}' happening on {date}.\n"
        f"Make it urgent, dramatic. End with: 'Here is everything you need to know and how YOUR sign is affected.'\n"
        f"Maximum 65 words.", max_tokens=200
    )
    sections.append(hook)

    # What is this transit?
    explainer = _call_groq(
        f"Write a 3-minute spoken section explaining the astrological significance of: '{event}'.\n\n"
        f"Background: {desc}\n\n"
        f"Cover: what this transit means cosmically, its historical significance, "
        f"how often it happens, the themes it governs, its general effects on humanity, "
        f"and the overall energy it brings to the coming weeks.\n\n"
        f"Write 280 to 320 words. Authoritative and engaging.", max_tokens=900
    )
    sections.append(explainer)

    # Impact on all 12 signs
    print(f"   Writing transit impacts for all 12 signs...")
    for sign in ZODIAC_SIGNS:
        sd = SIGN_DATA[sign]
        impact = _call_groq(
            f"Write a 40-second spoken section about how '{event}' specifically affects {sign} "
            f"({sd['element']} sign, ruled by {sd['planet']}).\n\n"
            f"Be specific about: which life area is impacted for {sign}, "
            f"what challenge or opportunity this brings, and one piece of practical advice for {sign}.\n\n"
            f"Start with the sign name: '{sign}...'\n"
            f"Write 70 to 90 words.", max_tokens=280
        )
        sections.append(impact)

    # Closing
    closing = _call_groq(
        f"Write a 30-second warm closing for a YouTube video about '{event}'.\n"
        f"Encourage viewers to navigate this transit with awareness and grace. "
        f"Ask them to like, subscribe to {CHANNEL_NAME}, and comment which sign they are. "
        f"End with: 'The cosmos speaks. Are you listening? Namaste.'\n"
        f"Maximum 75 words.", max_tokens=220
    )
    sections.append(closing)

    full_script = "\n\n".join(s for s in sections if s)
    wc = len(full_script.split())
    print(f"   ✅ Transit special script: {wc:,} words (~{wc//140} min)")
    return _check_min_words(full_script, "transit", event)
# ─────────────────────────────────────────────────────────────

def build_omnibus_seo(astro_context: dict) -> tuple:
    """Returns (title, description, tags) for the weekly omnibus video."""
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
    """Returns (title, description, tags) for a per-sign video."""
    week = astro_context.get("week_label", "this week")
    year = datetime.now().year
    sd   = SIGN_DATA[sign]
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
    """Returns (title, description, tags) for a transit special video."""
    year  = datetime.now().year
    event = transit["event"]
    planet = transit["planet"]
    date  = transit["date"]

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
    """Return transit events that directly affect this sign."""
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
