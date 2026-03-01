# ============================================================
#  astro_video_renderer.py
#  Renders beautiful cosmic-themed video slides for astrology
#  content. Produces 1280×720 landscape videos.
#
#  Slides produced:
#  0. Hook Card         — dramatic opener, sign symbols ring
#  1. Weekly Overview   — planetary positions table
#  2. Sign Section      — per-sign horoscope (repeated 12x)
#  3. Transit Special   — planet glyph + impact breakdown
#  4. Closing           — channel CTA
# ============================================================

import os
import math
import asyncio
import textwrap
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont
import edge_tts

try:
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
    MOVIEPY_V2 = True
except ImportError:
    from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
    MOVIEPY_V2 = False

from astro_config import (
    ASTRO_VOICE_FILE, ASTRO_OUTPUT_VIDEO,
    TTS_VOICE, TTS_VOICE_ALT, VIDEO_FPS, VIDEO_CODEC, AUDIO_CODEC,
    BRAND_BG_COLOR, BRAND_PRIMARY_COLOR, BRAND_ACCENT_COLOR,
    BRAND_GLOW_COLOR, CHANNEL_NAME, SIGN_DATA, ZODIAC_SIGNS
)

W, H = 1280, 720

# ─────────────────────────────────────────────────────────────
# Font helpers
# ─────────────────────────────────────────────────────────────
_FONT_CACHE = {}

def _font(size: int, bold: bool = True) -> ImageFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = (
        [r"C:\Windows\Fonts\arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]
        if bold else
        [r"C:\Windows\Fonts\arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/TTF/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/freefont/FreeSans.ttf"]
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

def _cx(draw, y, text, font, fill, shadow=(0, 0, 0), off=3):
    w, _ = _tw(draw, text, font)
    x = (W - w) // 2
    draw.text((x + off, y + off), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)

def _shadow_text(draw, x, y, text, font, fill, off=3):
    draw.text((x + off, y + off), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


# ─────────────────────────────────────────────────────────────
# Background generators
# ─────────────────────────────────────────────────────────────

def _cosmic_bg(p_color: tuple = None) -> Image.Image:
    """
    Deep space background with subtle star field and
    gradient from cosmic purple to near-black.
    """
    img  = Image.new("RGB", (W, H), BRAND_BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Gradient
    c1 = BRAND_BG_COLOR
    c2 = (15, 5, 40)
    for y in range(H):
        t = y / H
        r = int(c1[0] * (1-t) + c2[0] * t)
        g = int(c1[1] * (1-t) + c2[1] * t)
        b = int(c1[2] * (1-t) + c2[2] * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Star field
    import random
    rng = random.Random(42)
    for _ in range(280):
        sx  = rng.randint(0, W)
        sy  = rng.randint(0, H)
        sz  = rng.choice([1, 1, 1, 2])
        bri = rng.randint(120, 255)
        draw.ellipse([sx, sy, sx+sz, sy+sz], fill=(bri, bri, bri))

    # Subtle glow orbs
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od   = ImageDraw.Draw(over)
    # Left glow
    for r_ in range(180, 0, -10):
        a = int(30 * (1 - r_/180))
        od.ellipse([-60, H//2-r_, -60+r_*2, H//2+r_], fill=BRAND_PRIMARY_COLOR+(a,))
    # Right glow
    for r_ in range(160, 0, -10):
        a = int(25 * (1 - r_/160))
        od.ellipse([W-r_*2+60, H-r_*2+60, W+60, H+60], fill=(0, 100, 200, a))

    img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")

    # Optional sign color tint
    if p_color:
        tint = Image.new("RGBA", (W, H), p_color + (18,))
        img  = Image.alpha_composite(img.convert("RGBA"), tint).convert("RGB")

    return img


def _top_bar(draw, title: str, subtitle: str = ""):
    draw.rectangle([0, 0, W, 72], fill=(0, 0, 0))
    draw.rectangle([0, 0, 5, 72],  fill=BRAND_PRIMARY_COLOR)
    draw.rectangle([W-5, 0, W, 72], fill=BRAND_PRIMARY_COLOR)
    tf = _font(26, bold=True)
    _cx(draw, 10, title[:90], tf, BRAND_ACCENT_COLOR)
    if subtitle:
        sf = _font(18, bold=False)
        _cx(draw, 44, subtitle, sf, (160, 160, 160))


def _bottom_bar(draw):
    draw.rectangle([0, H-40, W, H], fill=(0, 0, 0))
    bf = _font(18, bold=True)
    _cx(draw, H-33, f"🔮  {CHANNEL_NAME}  |  Subscribe for Weekly Cosmic Forecasts", bf, BRAND_ACCENT_COLOR)


def _sign_ring(draw, cx: int, cy: int, radius: int, highlight: str = None):
    """Draw all 12 zodiac symbols in a circle."""
    sf = _font(22, bold=True)
    for i, sign in enumerate(ZODIAC_SIGNS):
        angle = math.radians((i * 30) - 90)
        x = int(cx + radius * math.cos(angle))
        y = int(cy + radius * math.sin(angle))
        sd   = SIGN_DATA[sign]
        col  = sd["color"] if sign == highlight else (80, 80, 100)
        sym  = sd["symbol"]
        sw, sh = _tw(draw, sym, sf)
        if sign == highlight:
            # Glow ring
            draw.ellipse([x-20, y-20, x+20, y+20], fill=sd["color"] + (0,),
                         outline=sd["color"], width=2)
        draw.text((x - sw//2, y - sh//2), sym, font=sf, fill=col)


# ─────────────────────────────────────────────────────────────
# SLIDE MAKERS
# ─────────────────────────────────────────────────────────────

def make_hook_slide(week_label: str, major_transits: list) -> str:
    img  = _cosmic_bg()
    draw = ImageDraw.Draw(img)

    _top_bar(draw, f"🔮  {CHANNEL_NAME}  —  Weekly Cosmic Forecast")

    # Large channel title
    tf = _font(68, bold=True)
    _cx(draw, 90, "WEEKLY HOROSCOPE", tf, BRAND_ACCENT_COLOR)

    tf2 = _font(38, bold=False)
    _cx(draw, 170, week_label, tf2, (200, 180, 255))

    # Sign ring
    _sign_ring(draw, W//2, 390, 195)

    # Center cosmic eye / glyph
    cx, cy = W//2, 390
    for r in range(50, 0, -5):
        a = int(80 * (1 - r/50))
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=BRAND_PRIMARY_COLOR+(a,))
    draw.ellipse([cx-50, cy-50, cx+50, cy+50], outline=BRAND_ACCENT_COLOR, width=2)
    mf = _font(36, bold=True)
    _cx(draw, cy - 18, "✦", mf, BRAND_ACCENT_COLOR)

    # Major transit pills
    if major_transits:
        pill_y = 570
        for t in major_transits[:3]:
            label = f"⚡ {t['event'][:50]}"
            lf    = _font(22, bold=True)
            lw, _ = _tw(draw, label, lf)
            px    = (W - lw - 40) // 2
            draw.rounded_rectangle([px-10, pill_y-5, px+lw+30, pill_y+28],
                                    radius=14, fill=(60, 0, 120))
            draw.text((px + 10, pill_y), label, font=lf, fill=BRAND_ACCENT_COLOR)
            pill_y += 42

    _bottom_bar(draw)
    path = "_astro_s0_hook.jpg"
    img.save(path, quality=95)
    return path


def make_planet_overview_slide(positions: dict, week_label: str) -> str:
    img  = _cosmic_bg()
    draw = ImageDraw.Draw(img)

    _top_bar(draw, "🪐  Planetary Positions", f"Week of {week_label}")

    tf = _font(38, bold=True)
    _cx(draw, 82, "THIS WEEK'S COSMIC MAP", tf, BRAND_ACCENT_COLOR)

    # Two-column planet table
    planets_list = list(positions.items())
    col_w  = W // 2 - 60
    start_y = 140
    row_h   = 46

    pf  = _font(24, bold=True)
    pf2 = _font(22, bold=False)

    for i, (planet, data) in enumerate(planets_list):
        col   = i % 2
        row   = i // 2
        x     = 60 + col * (col_w + 60)
        y     = start_y + row * row_h
        retro = " ℞" if data.get("retrograde") else ""
        sign  = data.get("sign", "?")
        deg   = data.get("degree", 0)
        sdata = SIGN_DATA.get(sign, {})
        sym   = sdata.get("symbol", "✦")
        col_c = sdata.get("color", BRAND_ACCENT_COLOR)

        # Planet name
        draw.text((x, y), f"{planet}:", font=pf, fill=(200, 180, 255))
        # Sign + degree
        val = f"{sym} {sign} {deg:.0f}°{retro}"
        draw.text((x + 160, y), val, font=pf2, fill=col_c)

    # Element balance
    el_y = start_y + (len(planets_list)//2 + 1) * row_h + 20
    draw.line([(60, el_y), (W-60, el_y)], fill=(60, 40, 100), width=1)
    ef = _font(28, bold=True)
    _cx(draw, el_y + 10, "✦  Cosmic Energy Summary  ✦", ef, BRAND_ACCENT_COLOR)

    el_counts = {"Fire": 0, "Earth": 0, "Air": 0, "Water": 0}
    for _, data in positions.items():
        s = data.get("sign", "")
        el = SIGN_DATA.get(s, {}).get("element", "")
        if el in el_counts:
            el_counts[el] += 1

    el_colors = {"Fire": (220, 80, 30), "Earth": (80, 180, 80),
                 "Air": (200, 200, 100), "Water": (60, 130, 220)}
    el_x = 120
    for el, cnt in el_counts.items():
        label = f"{el}: {cnt}"
        ef2   = _font(24, bold=True)
        draw.text((el_x, el_y + 46), label, font=ef2, fill=el_colors[el])
        el_x += 250

    _bottom_bar(draw)
    path = "_astro_s1_planets.jpg"
    img.save(path, quality=95)
    return path


def make_sign_slide(sign: str, week_label: str, positions: dict, sign_transits: list) -> str:
    sd   = SIGN_DATA[sign]
    img  = _cosmic_bg(p_color=sd["color"])
    draw = ImageDraw.Draw(img)

    _top_bar(draw, f"{sd['symbol']}  {sign.upper()} WEEKLY HOROSCOPE", f"Week of {week_label}")

    # Large symbol
    sym_f = _font(130, bold=True)
    sym_w, sym_h = _tw(draw, sd["symbol"], sym_f)
    # Left side glow
    for gi in range(40, 0, -5):
        a = int(60 * (1 - gi/40))
        draw.ellipse([60 - gi, 90 - gi, 60 + sym_w + gi, 90 + sym_h + gi],
                     fill=sd["color"] + (a,))
    draw.text((60, 90), sd["symbol"], font=sym_f, fill=sd["color"])

    # Sign name
    sn_f = _font(72, bold=True)
    draw.text((240, 100), sign.upper(), font=sn_f, fill=(255, 255, 255))

    # Dates + Element + Planet
    info_f = _font(26, bold=False)
    draw.text((242, 185), f"{sd['dates']}  |  {sd['element']}  |  ♟ {sd['planet']}", font=info_f, fill=(180, 160, 220))

    # Horizontal divider
    draw.line([(60, 250), (W-60, 250)], fill=(80, 60, 120), width=1)

    # Ruling planet position
    rp     = positions.get(sd["planet"], {})
    rp_sign = rp.get("sign", "?")
    rp_deg  = rp.get("degree", 0)
    rp_ret  = " Retrograde ℞" if rp.get("retrograde") else ""
    rp_str  = f"Your ruling planet {sd['planet']} is in {rp_sign} {rp_deg:.0f}°{rp_ret}"
    rp_f    = _font(26, bold=True)
    _cx(draw, 260, rp_str[:80], rp_f, BRAND_ACCENT_COLOR)

    # Transits affecting this sign
    if sign_transits:
        draw.line([(60, 300), (W-60, 300)], fill=(60, 40, 100), width=1)
        th_f = _font(24, bold=True)
        draw.text((60, 310), "⚡ KEY TRANSITS THIS WEEK:", font=th_f, fill=BRAND_GLOW_COLOR)
        ty = 342
        tf2 = _font(22, bold=False)
        for t in sign_transits[:4]:
            draw.text((80, ty), f"• {t['event']} — {t['date']}", font=tf2, fill=(200, 190, 230))
            ty += 30

    # Life area indicator pills
    areas = [("💕 LOVE", sd["color"]), ("💼 CAREER", (100, 100, 200)),
             ("💰 MONEY", (180, 150, 0)), ("🌿 HEALTH", (50, 160, 80))]
    pill_x, pill_y = 60, H - 140
    for label, col in areas:
        lf  = _font(22, bold=True)
        lw, lh = _tw(draw, label, lf)
        draw.rounded_rectangle([pill_x - 8, pill_y - 4, pill_x + lw + 8, pill_y + lh + 4],
                                radius=12, fill=col)
        draw.text((pill_x, pill_y), label, font=lf, fill=(255, 255, 255))
        pill_x += lw + 30

    # Channel branding
    _bottom_bar(draw)
    path = f"_astro_sign_{sign.lower()}.jpg"
    img.save(path, quality=95)
    return path


def make_transit_special_slide(transit: dict, sign: str = None) -> str:
    img  = _cosmic_bg()
    draw = ImageDraw.Draw(img)

    event  = transit["event"]
    planet = transit["planet"]
    date   = transit["date"]
    desc   = transit["description"]

    _top_bar(draw, f"⚡  MAJOR COSMIC EVENT", f"Occurring: {date}")

    # Event title
    ef = _font(54, bold=True)
    _cx(draw, 90, event.upper()[:50], ef, BRAND_ACCENT_COLOR)

    ef2 = _font(28, bold=False)
    _cx(draw, 158, date, ef2, (180, 160, 220))

    # Description
    draw.line([(60, 205), (W-60, 205)], fill=(80, 60, 120), width=1)
    desc_f = _font(24, bold=False)
    words  = desc.split()
    lines  = []
    line   = ""
    for w in words:
        test = (line + " " + w).strip()
        tw, _ = _tw(draw, test, desc_f)
        if tw <= W - 140:
            line = test
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    dy = 218
    for ln in lines[:5]:
        draw.text((70, dy), ln, font=desc_f, fill=(200, 190, 230))
        dy += 32

    # Affected signs
    af_signs = transit.get("affected_signs", [])
    if af_signs:
        draw.line([(60, dy + 10), (W-60, dy + 10)], fill=(60, 40, 100), width=1)
        lf = _font(24, bold=True)
        draw.text((60, dy + 22), "SIGNS MOST AFFECTED:", font=lf, fill=BRAND_GLOW_COLOR)
        sx = 60
        sy = dy + 60
        for s in af_signs[:6]:
            sdat = SIGN_DATA.get(s, {})
            sym  = sdat.get("symbol", "✦")
            col  = sdat.get("color", BRAND_ACCENT_COLOR)
            sf_  = _font(28, bold=True)
            lbl  = f"{sym} {s}"
            lw, _ = _tw(draw, lbl, sf_)
            draw.text((sx, sy), lbl, font=sf_, fill=col)
            sx += lw + 30
            if sx > W - 200:
                sx  = 60
                sy += 38

    # Intensity badge
    intensity = transit.get("intensity", "medium")
    badge_col = (200, 0, 0) if intensity == "high" else (150, 100, 0)
    bx = W - 220
    draw.rounded_rectangle([bx, 88, bx+180, 128], radius=20, fill=badge_col)
    bf = _font(26, bold=True)
    draw.text((bx + 20, 96), f"⚡ {intensity.upper()} IMPACT", font=bf, fill=(255, 255, 255))

    _bottom_bar(draw)
    path = f"_astro_transit_{planet.lower()}.jpg"
    img.save(path, quality=95)
    return path


def make_closing_slide(week_label: str) -> str:
    img  = _cosmic_bg()
    draw = ImageDraw.Draw(img)

    _top_bar(draw, f"🔮  {CHANNEL_NAME}", "Thank you for watching!")

    tf = _font(62, bold=True)
    _cx(draw, 100, "MAY THE STARS", tf, BRAND_ACCENT_COLOR)
    tf2 = _font(62, bold=True)
    _cx(draw, 172, "GUIDE YOUR PATH", tf2, BRAND_ACCENT_COLOR)

    nf = _font(34, bold=False)
    _cx(draw, 260, f"Weekly Horoscope — {week_label}", nf, (180, 160, 220))

    draw.line([(120, 318), (W-120, 318)], fill=(80, 60, 120), width=1)

    actions = [
        ("👍", "LIKE this video"),
        ("🔔", f"SUBSCRIBE to {CHANNEL_NAME}"),
        ("💬", "COMMENT your zodiac sign"),
        ("📲", "SHARE with your cosmic tribe"),
    ]
    af = _font(30, bold=True)
    ay = 340
    for icon, text in actions:
        _cx(draw, ay, f"{icon}  {text}", af, (220, 200, 255))
        ay += 52

    # Namaste closing
    nc = _font(42, bold=True)
    _cx(draw, 560, "🙏  Namaste  🙏", nc, BRAND_ACCENT_COLOR)

    # Sign symbols row
    sf_ = _font(28, bold=True)
    all_syms = "  ".join([SIGN_DATA[s]["symbol"] for s in ZODIAC_SIGNS])
    _cx(draw, 620, all_syms, sf_, (100, 80, 160))

    _bottom_bar(draw)
    path = "_astro_closing.jpg"
    img.save(path, quality=95)
    return path


# ─────────────────────────────────────────────────────────────
# TTS + Render
# ─────────────────────────────────────────────────────────────

async def _tts_async(text: str, voice: str, output: str):
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output)
    except Exception:
        communicate = edge_tts.Communicate(text, TTS_VOICE_ALT)
        await communicate.save(output)


def generate_voiceover(script: str, output_file: str = None) -> float:
    """Generate TTS voiceover. Returns duration in seconds."""
    out = output_file or ASTRO_VOICE_FILE
    wc  = len(script.split())
    print(f"   🎙️  Generating voiceover ({wc:,} words, ~{wc//140} min)...")
    try:
        asyncio.run(_tts_async(script, TTS_VOICE, out))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_tts_async(script, TTS_VOICE, out))
        loop.close()

    if not os.path.exists(out) or os.path.getsize(out) < 500:
        raise RuntimeError(f"TTS failed: {out}")

    audio = AudioFileClip(out)
    dur   = audio.duration
    audio.close()
    print(f"   ✅ Audio: {dur:.1f}s ({dur/60:.1f} min)")
    return dur


def _make_clip(path: str, duration: float):
    clip = ImageClip(path)
    if MOVIEPY_V2:
        clip = clip.with_duration(duration)
    else:
        clip = clip.set_duration(duration)
    return clip


def render_astro_video(
    script: str,
    astro_context: dict,
    slide_paths: list,
    output_file: str = None,
) -> str:
    """
    Render the full astrology video.
    slide_paths: ordered list of .jpg paths (hook → ... → closing)
    Returns path to rendered .mp4
    """
    out = output_file or ASTRO_OUTPUT_VIDEO

    # 1. Voiceover
    audio_dur = generate_voiceover(script, ASTRO_VOICE_FILE)

    # 2. Proportional durations
    n = len(slide_paths)
    if n == 0:
        raise RuntimeError("No slides provided to render_astro_video")

    # First and last slide get slightly more time (hook + closing)
    weights = [1.5] + [1.0] * (n - 2) + [1.2] if n > 2 else [1.0] * n
    total_w = sum(weights)
    durations = [audio_dur * w / total_w for w in weights]

    # Fix float drift
    diff = audio_dur - sum(durations)
    durations[-1] += diff

    print(f"   🖼️  Building {n} slides...")
    clips = []
    for i, (path, dur) in enumerate(zip(slide_paths, durations)):
        if dur <= 0:
            continue
        clip = _make_clip(path, dur)
        clips.append(clip)
        print(f"      Clip {i}: {os.path.basename(path)} → {dur:.1f}s")

    # 3. Concatenate + audio
    video = concatenate_videoclips(clips, method="compose") if len(clips) > 1 else clips[0]
    audio = AudioFileClip(ASTRO_VOICE_FILE)

    if MOVIEPY_V2:
        final = video.with_audio(audio)
    else:
        final = video.set_audio(audio)

    # 4. Write
    print(f"   🔄 Rendering {audio_dur/60:.1f} min video → {out}...")
    kw = dict(fps=VIDEO_FPS, codec=VIDEO_CODEC, audio_codec=AUDIO_CODEC, threads=4, logger="bar")
    if not MOVIEPY_V2:
        kw["preset"] = "fast"
    final.write_videofile(out, **kw)

    # 5. Cleanup
    for p in slide_paths:
        try:
            os.remove(p)
        except Exception:
            pass

    if not os.path.exists(out) or os.path.getsize(out) < 5000:
        raise RuntimeError(f"Render failed: {out}")

    print(f"   ✅ Video: {out} ({os.path.getsize(out)/1e6:.1f} MB)")
    return out
