# ============================================================
#  astro_shorts.py
#  Generates a 45-second YouTube Short for each zodiac sign.
#  Called automatically after the per-sign video uploads.
#
#  FORMAT: 1080×1920 vertical (9:16)
#  DURATION: 44-47 seconds
#
#  SLIDES:
#  0:00-0:06  Hook — sign symbol + dramatic question
#  0:06-0:20  Key planetary influences this week
#  0:20-0:35  Love / Career / Health quick bullets
#  0:35-0:45  Lucky day + Oracle message + Subscribe CTA
# ============================================================

import os
import re
import asyncio
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import edge_tts

try:
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
    MOVIEPY_V2 = True
except ImportError:
    from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
    MOVIEPY_V2 = False

from astro_config import (
    TTS_VOICE, TTS_VOICE_ALT, VIDEO_FPS, VIDEO_CODEC, AUDIO_CODEC,
    BRAND_BG_COLOR, BRAND_PRIMARY_COLOR, BRAND_ACCENT_COLOR, BRAND_GLOW_COLOR,
    CHANNEL_NAME, CHANNEL_HANDLE, SIGN_DATA, GROQ_API_KEY, ASTRO_SHORT_VIDEO,
    ASTRO_SHORT_VOICE, ASTRO_SHORT_THUMB
)

SW, SH = 1080, 1920
_FONT_CACHE = {}


def _font(size: int, bold: bool = True) -> ImageFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = (
        [r"C:\Windows\Fonts\arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
        if bold else
        [r"C:\Windows\Fonts\arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/TTF/DejaVuSans.ttf"]
    )
    for p in candidates:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _FONT_CACHE[key] = f
                return f
            except Exception:
                continue
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def _cx(draw, y, text, font, fill, shadow_off=4):
    w, _ = _tw(draw, text, font)
    x = (SW - w) // 2
    draw.text((x + shadow_off, y + shadow_off), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


def _cosmic_short_bg(sign_color: tuple) -> Image.Image:
    img  = Image.new("RGBA", (SW, SH), BRAND_BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)
    c1, c2 = BRAND_BG_COLOR, (20, 5, 50)
    for y in range(SH):
        t = y / SH
        r = int(c1[0]*(1-t) + c2[0]*t)
        g = int(c1[1]*(1-t) + c2[1]*t)
        b = int(c1[2]*(1-t) + c2[2]*t)
        draw.line([(0, y), (SW, y)], fill=(r, g, b, 255))
    import random
    rng = random.Random(123)
    for _ in range(400):
        sx, sy = rng.randint(0, SW), rng.randint(0, SH)
        bri    = rng.randint(80, 220)
        sz     = rng.choice([1, 1, 2])
        draw.ellipse([sx, sy, sx+sz, sy+sz], fill=(bri, bri, bri, bri))
    over = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    od   = ImageDraw.Draw(over)
    for r_ in range(300, 0, -20):
        a = int(40 * (1 - r_/300))
        od.ellipse([SW//2-r_, SH//2-r_, SW//2+r_, SH//2+r_], fill=sign_color+(a,))
    return Image.alpha_composite(img, over).convert("RGB")


def make_short_hook(sign: str, week_label: str, sd: dict) -> str:
    img  = _cosmic_short_bg(sd["color"])
    draw = ImageDraw.Draw(img)

    # Top badge
    draw.rounded_rectangle([SW//2-240, 80, SW//2+240, 150], radius=35, fill=BRAND_PRIMARY_COLOR)
    _cx(draw, 95, "🔮  WEEKLY HOROSCOPE", _font(36, bold=True), (255, 255, 255))

    # Week label
    _cx(draw, 180, week_label, _font(38, bold=False), (200, 180, 255))

    # Giant sign symbol
    sym_f = _font(380, bold=True)
    sym   = sd["symbol"]
    sw_, sh_ = _tw(draw, sym, sym_f)
    draw.text((SW//2 - sw_//2 + 5, 220 + 5), sym, font=sym_f, fill=(0, 0, 0))
    draw.text((SW//2 - sw_//2, 220),          sym, font=sym_f, fill=sd["color"])

    # Sign name
    sn_f = _font(110, bold=True)
    _cx(draw, 680, sign.upper(), sn_f, (255, 255, 255))

    # Dates
    _cx(draw, 808, sd["dates"], _font(44, bold=False), sd["color"])

    # Element pill
    el_f = _font(36, bold=True)
    elw, _ = _tw(draw, sd["element"], el_f)
    ex = (SW - elw - 40) // 2
    draw.rounded_rectangle([ex-10, 870, ex+elw+30, 870+54], radius=27, fill=sd["color"])
    draw.text((ex+10, 878), sd["element"], font=el_f, fill=(255, 255, 255))

    # Hook question
    qf = _font(60, bold=True)
    _cx(draw, 970, "WHAT'S IN STORE FOR", qf, BRAND_ACCENT_COLOR)
    _cx(draw, 1046, f"YOU THIS WEEK? 🔮", qf, BRAND_ACCENT_COLOR)

    # Watch prompt
    _cx(draw, 1150, "Watch till the end 👇", _font(44, bold=False), (160, 160, 160))

    # Channel + CTA
    draw.rectangle([0, SH-200, SW, SH-120], fill=(0, 0, 0))
    _cx(draw, SH-192, f"🔮  {CHANNEL_NAME}", _font(40, bold=True), BRAND_ACCENT_COLOR)
    draw.rounded_rectangle([80, SH-110, SW-80, SH-30], radius=40, fill=(255, 0, 0))
    _cx(draw, SH-102, "🔔  SUBSCRIBE FOR WEEKLY PICKS", _font(38, bold=True), (255, 255, 255))

    path = f"_ashort_{sign.lower()}_s1.jpg"
    img.save(path, quality=95)
    return path


def make_short_planet_slide(sign: str, week_label: str, sd: dict, positions: dict, sign_transits: list) -> str:
    img  = _cosmic_short_bg(sd["color"])
    draw = ImageDraw.Draw(img)

    _cx(draw, 80, "🪐  PLANETARY INFLUENCES", _font(48, bold=True), BRAND_ACCENT_COLOR)
    _cx(draw, 150, f"For {sign} — {week_label}", _font(36, bold=False), (180, 160, 220))
    draw.line([(60, 210), (SW-60, 210)], fill=(80, 60, 120), width=2)

    # Ruling planet info
    rp     = positions.get(sd["planet"], {})
    rp_s   = rp.get("sign", "?")
    rp_d   = rp.get("degree", 0)
    rp_ret = " Retrograde ℞" if rp.get("retrograde") else ""
    rp_txt = f"♟ {sd['planet']} in {rp_s} {rp_d:.0f}°{rp_ret}"

    rp_f = _font(44, bold=True)
    draw.rounded_rectangle([60, 235, SW-60, 235+70], radius=16, fill=sd["color"])
    _cx(draw, 250, rp_txt[:45], rp_f, (255, 255, 255))

    # Transit cards
    ty = 340
    for i, t in enumerate(sign_transits[:5]):
        col   = sd["color"] if i % 2 == 0 else BRAND_PRIMARY_COLOR
        darker = tuple(max(0, c-70) for c in col)
        draw.rounded_rectangle([60, ty, SW-60, ty+110], radius=20, fill=darker)
        draw.rounded_rectangle([60, ty, 80, ty+110], radius=10, fill=col)
        ef  = _font(34, bold=True)
        ef2 = _font(28, bold=False)
        _cx(draw, ty+12, t.get("event", "")[:42], ef, col)
        _cx(draw, ty+58, t.get("date", ""), ef2, (180, 160, 200))
        ty += 130

    if not sign_transits:
        gf = _font(38, bold=False)
        _cx(draw, 500, "General cosmic energies apply", gf, (160, 140, 180))
        _cx(draw, 560, "Focus on inner alignment", gf, (160, 140, 180))

    draw.line([(60, SH-250), (SW-60, SH-250)], fill=(60, 40, 100), width=2)
    _cx(draw, SH-234, "Next: Love 💕 Career 💼 Health 🌿", _font(38, bold=True), BRAND_ACCENT_COLOR)
    draw.rectangle([0, SH-180, SW, SH-100], fill=(0, 0, 0))
    _cx(draw, SH-172, f"🔮  {CHANNEL_NAME}", _font(38, bold=True), BRAND_ACCENT_COLOR)
    draw.rounded_rectangle([80, SH-90, SW-80, SH-20], radius=35, fill=(255, 0, 0))
    _cx(draw, SH-82, "👍 LIKE  •  🔔 SUBSCRIBE", _font(36, bold=True), (255, 255, 255))

    path = f"_ashort_{sign.lower()}_s2.jpg"
    img.save(path, quality=95)
    return path


def make_short_areas_slide(sign: str, sd: dict, predictions: dict) -> str:
    img  = _cosmic_short_bg(sd["color"])
    draw = ImageDraw.Draw(img)

    sym_f = _font(80, bold=True)
    _cx(draw, 80, f"{sd['symbol']}  {sign.upper()}  {sd['symbol']}", sym_f, sd["color"])
    _cx(draw, 178, "YOUR WEEK AT A GLANCE", _font(44, bold=True), BRAND_ACCENT_COLOR)
    draw.line([(60, 246), (SW-60, 246)], fill=(80, 60, 120), width=2)

    areas = [
        ("💕", "LOVE",    predictions.get("love",   "Romantic energy is flowing your way")),
        ("💼", "CAREER",  predictions.get("career", "Career momentum builds steadily")),
        ("💰", "MONEY",   predictions.get("money",  "Watch spending — savings favoured")),
        ("🌿", "HEALTH",  predictions.get("health", "Rest and self-care are your priority")),
    ]

    card_y = 270
    for icon, label, text in areas:
        col = sd["color"]
        darker = tuple(max(0, c-80) for c in col)
        draw.rounded_rectangle([60, card_y, SW-60, card_y+155], radius=24, fill=darker)
        draw.rounded_rectangle([60, card_y, 90, card_y+155], radius=12, fill=col)

        # Icon + Label
        il_f = _font(46, bold=True)
        draw.text((100, card_y+15), f"{icon}  {label}", font=il_f, fill=col)

        # Body text (wrapped)
        bf   = _font(34, bold=False)
        words = text.split()
        lines, line = [], ""
        for w in words:
            test = (line + " " + w).strip()
            tw_, _ = _tw(draw, test, bf)
            if tw_ <= SW - 200:
                line = test
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)
        ty2 = card_y + 68
        for ln in lines[:2]:
            _cx(draw, ty2, ln, bf, (210, 200, 230))
            ty2 += 40

        card_y += 175

    draw.rectangle([0, SH-180, SW, SH-100], fill=(0, 0, 0))
    _cx(draw, SH-172, f"🔮  {CHANNEL_NAME}", _font(38, bold=True), BRAND_ACCENT_COLOR)
    draw.rounded_rectangle([80, SH-90, SW-80, SH-20], radius=35, fill=(255, 0, 0))
    _cx(draw, SH-82, "👍 LIKE  •  🔔 SUBSCRIBE", _font(36, bold=True), (255, 255, 255))

    path = f"_ashort_{sign.lower()}_s3.jpg"
    img.save(path, quality=95)
    return path


def make_short_oracle_slide(sign: str, sd: dict, oracle_msg: str, lucky_day: str, lucky_num: int) -> str:
    img  = _cosmic_short_bg(sd["color"])
    draw = ImageDraw.Draw(img)

    _cx(draw, 90, "🌟  ORACLE MESSAGE", _font(52, bold=True), BRAND_ACCENT_COLOR)
    _cx(draw, 165, f"For {sign}  {sd['symbol']}", _font(44, bold=False), sd["color"])
    draw.line([(80, 228), (SW-80, 228)], fill=(80, 60, 120), width=2)

    # Oracle message card
    om_f = _font(40, bold=False)
    words, lines, line = oracle_msg.split(), [], ""
    for w in words:
        test = (line + " " + w).strip()
        tw_, _ = _tw(draw, test, om_f)
        if tw_ <= SW - 140:
            line = test
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)

    msg_h   = len(lines) * 52 + 40
    msg_top = 260
    draw.rounded_rectangle([60, msg_top, SW-60, msg_top+msg_h], radius=24, fill=(30, 0, 70))
    draw.rounded_rectangle([60, msg_top, 82, msg_top+msg_h], radius=12, fill=sd["color"])
    ty = msg_top + 20
    for idx, ln in enumerate(lines[:5]):
        # Opening quote on first line only, closing quote on last line only
        if len(lines) == 1:
            display = f'"{ln}"'
        elif idx == 0:
            display = f'"{ln}'
        elif idx == min(4, len(lines) - 1):
            display = f'{ln}"'
        else:
            display = ln
        _cx(draw, ty, display, om_f, (230, 220, 255))
        ty += 52

    # Lucky items
    lucky_y = msg_top + msg_h + 40
    for label, val, col in [
        ("🗓️  LUCKY DAY",    lucky_day, BRAND_ACCENT_COLOR),
        ("🔢  LUCKY NUMBER", str(lucky_num), (180, 255, 180)),
    ]:
        draw.rounded_rectangle([80, lucky_y, SW-80, lucky_y+85], radius=20, fill=(0, 0, 0))
        lf = _font(36, bold=True)
        vf = _font(42, bold=True)
        lw, _ = _tw(draw, label, lf)
        draw.text((100, lucky_y+12), label, font=lf, fill=(160, 140, 180))
        draw.text((100, lucky_y+46), val,   font=vf, fill=col)
        lucky_y += 105

    # Subscribe CTA
    cta_y = SH - 330
    draw.rounded_rectangle([60, cta_y, SW-60, cta_y+120], radius=30, fill=(255, 0, 0))
    _cx(draw, cta_y+15,  "🔔  SUBSCRIBE TO", _font(42, bold=True), (255, 255, 255))
    _cx(draw, cta_y+65, f"{CHANNEL_NAME.upper()}", _font(46, bold=True), BRAND_ACCENT_COLOR)

    # Handle
    _cx(draw, SH-200, f"@{CHANNEL_HANDLE}", _font(40, bold=True), (180, 160, 220))

    # Engagement
    _cx(draw, SH-140, f"💬  Comment your birth date below!", _font(38, bold=True), BRAND_ACCENT_COLOR)

    # Footer
    draw.rectangle([0, SH-80, SW, SH], fill=(0, 0, 0))
    _cx(draw, SH-68, f"🔮  {CHANNEL_NAME}  |  Weekly Horoscopes", _font(30, bold=False), (100, 80, 140))

    path = f"_ashort_{sign.lower()}_s4.jpg"
    img.save(path, quality=95)
    return path


# ─────────────────────────────────────────────────────────────
# Short Script Generator
# ─────────────────────────────────────────────────────────────

def generate_sign_short_script(sign: str, week_label: str, sd: dict,
                                astro_context: dict) -> tuple:
    """
    Returns (script_text, predictions_dict, lucky_day, lucky_num, oracle_msg).
    """
    from astro_script_generator import _clean, _call_llm, _transits_for_sign

    sign_transits = _transits_for_sign(sign, astro_context.get("transits", []))
    week = week_label

    prompt = (
        f"Write a 45-second YouTube Shorts spoken script for a {sign} weekly horoscope for {week}.\n\n"
        f"Ruling planet {sd['planet']} | Element: {sd['element']}\n"
        f"Transits: {sign_transits if sign_transits else 'General cosmic energies'}\n\n"
        f"STRUCTURE:\n"
        f"1. Hook (5s): dramatic question — what does the cosmos have for {sign} this week?\n"
        f"2. Planetary influences (12s): ruling planet position, 1-2 key transits for {sign}\n"
        f"3. Quick forecast (15s): love in one sentence, career in one sentence, health in one sentence\n"
        f"4. Oracle & CTA (10s): one oracle message, lucky day, subscribe to {CHANNEL_NAME}\n\n"
        f"Write 90 to 110 words. Flowing spoken speech. No markdown. No lists. No percent symbol.\n"
        f"Do not mention AI."
    )

    week_id = week_label.replace(" ", "_").replace(",", "").replace("–", "-")
    fallback = (
        f"{sign}, the cosmos has powerful energy aligned for you this week. "
        f"Your ruling planet {sd['planet']} is activating new opportunities in love and career. "
        f"Love is expansive this week. Career momentum builds strongly. "
        f"Prioritise your health and rest on the weekend. "
        f"Your oracle message: trust the journey, {sign}. "
        f"Subscribe to {CHANNEL_NAME} for your full weekly reading. Namaste."
    )
    script = _call_llm(
        prompt,
        max_tokens=320,
        cache_label=f"short_{sign.lower()}_{week_id}_script",
        fallback_text=fallback,
    )

    # ── Extract per-area predictions from the generated script ──────────────
    # Ask the LLM to distill the script into 4 short slide lines.
    week_id = week_label.replace(" ", "_").replace(",", "").replace("–", "-")
    pred_prompt = (
        f"From this {sign} weekly horoscope script, extract exactly 4 short slide-caption lines "
        f"(10 words max each) — one for each area. "
        f"Reply with ONLY these 4 lines, in this exact order, one per line, no labels:\n"
        f"1. Love insight\n2. Career insight\n3. Money insight\n4. Health insight\n\n"
        f"Script:\n{script}"
    )
    pred_fallback = (
        f"Romantic energy is flowing your way\n"
        f"Career momentum builds this week\n"
        f"Financial awareness is favoured\n"
        f"Rest and balance are your focus"
    )
    pred_raw = _call_llm(
        pred_prompt,
        max_tokens=120,
        cache_label=f"short_{sign.lower()}_{week_id}_preds",
        fallback_text=pred_fallback,
    )
    pred_lines = [ln.strip() for ln in pred_raw.strip().splitlines() if ln.strip()]
    # Strip any leading "1." / "Love:" labels the model may add
    pred_lines = [re.sub(r'^[\d]+[.)]\s*|^[A-Za-z]+:\s*', '', ln) for ln in pred_lines]
    while len(pred_lines) < 4:
        pred_lines.append("")
    preds = {
        "love":   pred_lines[0] or "Romantic energy is flowing your way",
        "career": pred_lines[1] or "Career momentum builds this week",
        "money":  pred_lines[2] or "Financial awareness is favoured",
        "health": pred_lines[3] or "Rest and balance are your focus",
    }

    # ── Lucky day / number / oracle — try to extract from script ────────────
    import random
    days    = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    lucky_d = random.choice(days)
    lucky_n = random.randint(1, 33)
    oracle  = f"Trust the cosmic flow, dear {sign}. You are exactly where you need to be."

    return script, preds, lucky_d, lucky_n, oracle


# ─────────────────────────────────────────────────────────────
# Render Short
# ─────────────────────────────────────────────────────────────

async def _tts_async(text, voice, out):
    try:
        await edge_tts.Communicate(text, voice).save(out)
    except Exception:
        await edge_tts.Communicate(text, TTS_VOICE_ALT).save(out)


def _make_clip(path, dur):
    c = ImageClip(path)
    return c.with_duration(dur) if MOVIEPY_V2 else c.set_duration(dur)


def render_sign_short(sign: str, week_label: str, astro_context: dict,
                      positions: dict) -> str:
    """Render a complete Short for one zodiac sign. Returns video path."""
    sd            = SIGN_DATA[sign]
    sign_transits = [
        t for t in astro_context.get("transits", [])
        if sign in t.get("affected_signs", [])
    ]
    script, preds, lucky_day, lucky_num, oracle = generate_sign_short_script(
        sign, week_label, sd, astro_context
    )

    # TTS
    out_voice = ASTRO_SHORT_VOICE.replace(".mp3", f"_{sign.lower()}.mp3")

    async def _run_tts():
        await _tts_async(script, TTS_VOICE, out_voice)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, _run_tts()).result()
        else:
            loop.run_until_complete(_run_tts())
    except RuntimeError:
        asyncio.run(_run_tts())

    audio_clip = AudioFileClip(out_voice)
    audio_dur  = min(audio_clip.duration, 58.0)
    audio_clip.close()

    # Slides
    slides = [
        make_short_hook(sign, week_label, sd),
        make_short_planet_slide(sign, week_label, sd, positions, sign_transits),
        make_short_areas_slide(sign, sd, preds),
        make_short_oracle_slide(sign, sd, oracle, lucky_day, lucky_num),
    ]

    weights   = [0.13, 0.30, 0.35, 0.22]
    durations = [audio_dur * w for w in weights]
    total_w   = sum(durations)
    durations = [d * audio_dur / total_w for d in durations]

    clips = [_make_clip(p, d) for p, d in zip(slides, durations)]
    video = concatenate_videoclips(clips, method="compose") if len(clips) > 1 else clips[0]
    audio = AudioFileClip(out_voice)
    if audio.duration > audio_dur:
        audio = audio.with_end(audio_dur) if MOVIEPY_V2 else audio.subclip(0, audio_dur)

    final = video.with_audio(audio) if MOVIEPY_V2 else video.set_audio(audio)

    out_video = ASTRO_SHORT_VIDEO.replace(".mp4", f"_{sign.lower()}.mp4")
    kw = dict(fps=VIDEO_FPS, codec=VIDEO_CODEC, audio_codec=AUDIO_CODEC, threads=4, logger="bar")
    if not MOVIEPY_V2:
        kw["preset"] = "fast"
    final.write_videofile(out_video, **kw)

    # Thumbnail
    make_sign_short_thumbnail(sign, sd, week_label)

    for p in slides:
        try:
            os.remove(p)
        except Exception:
            pass

    print(f"   ⚡ Short rendered: {out_video}")
    return out_video


def make_sign_short_thumbnail(sign: str, sd: dict, week_label: str) -> str:
    """Vertical 1080×1920 thumbnail for the Short."""
    img  = _cosmic_short_bg(sd["color"])
    draw = ImageDraw.Draw(img)

    sym_f = _font(420, bold=True)
    sym   = sd["symbol"]
    sw_, _ = _tw(draw, sym, sym_f)
    draw.text((SW//2 - sw_//2 + 6, 180 + 6), sym, font=sym_f, fill=(0, 0, 0))
    draw.text((SW//2 - sw_//2, 180), sym, font=sym_f, fill=sd["color"])

    _cx(draw, 700, sign.upper(), _font(120, bold=True), (255, 255, 255))
    _cx(draw, 840, "WEEKLY HOROSCOPE", _font(52, bold=True), BRAND_ACCENT_COLOR)
    _cx(draw, 920, week_label, _font(40, bold=False), (180, 160, 220))

    draw.rounded_rectangle([80, 1020, SW-80, 1110], radius=30, fill=(255, 0, 0))
    _cx(draw, 1032, "🔔  SUBSCRIBE NOW", _font(52, bold=True), (255, 255, 255))

    _cx(draw, 1160, f"💬  Comment your birth date!", _font(44, bold=True), BRAND_ACCENT_COLOR)
    _cx(draw, 1240, f"@{CHANNEL_HANDLE}", _font(40, bold=True), (180, 160, 220))

    out = ASTRO_SHORT_THUMB.replace(".jpg", f"_{sign.lower()}.jpg")
    img.save(out, quality=95)
    return out


def build_sign_short_seo(sign: str, week_label: str, astro_context: dict) -> tuple:
    """Returns (title, description, tags) for a sign Short upload."""
    sd   = SIGN_DATA[sign]
    year = datetime.now().year
    title = f"{sign} {sd['symbol']} Weekly Horoscope {week_label} #Shorts"
    if len(title) > 100:
        title = f"{sign} Weekly Horoscope {week_label} #Shorts"

    desc = f"""{sign} weekly horoscope for {week_label} in 45 seconds! 🔮

{sd['symbol']} {sign} ({sd['dates']}) — {sd['element']} Sign | Ruled by {sd['planet']}

🔔 Subscribe to {CHANNEL_NAME} for full weekly {sign} readings!
💬 Comment your birth date below!

#{sign} #{sign}Horoscope #WeeklyHoroscope{year} #Shorts
#Astrology #ZodiacSigns #{sign}Weekly #AstroOracle #CosmicForecast"""[:4950]

    raw_tags = [
        f"{sign.lower()} horoscope",
        f"{sign.lower()} weekly",
        f"{sign.lower()} shorts",
        "weekly horoscope shorts",
        "astrology shorts",
        f"horoscope {year}",
        "zodiac horoscope",
        "astrology reading",
        sign.lower(),
    ]
    FORBIDDEN = re.compile(r'[,<>&"\'\u2014\u2013]')
    seen, tags, total = set(), [], 0
    for tag in raw_tags:
        tag = FORBIDDEN.sub('', tag).strip()
        if not tag or len(tag) < 3:
            continue
        if len(tag) > 30:
            tag = tag[:30]
        low = tag.lower()
        cost = len(tag) + 1
        if low not in seen and total + cost <= 498:
            seen.add(low)
            tags.append(tag)
            total += cost

    return title[:100], desc, tags
