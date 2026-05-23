# ============================================================
#  astro_thumbnail.py
#  Generates stunning cosmic thumbnails for 3 video types:
#  1. Weekly Omnibus  — all 12 signs ring + week label
#  2. Per-Sign        — large sign symbol + glow + key insight
#  3. Transit Special — planet glyph + dramatic event title
# ============================================================

import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from astro_config import (
    ASTRO_THUMBNAIL,
    BRAND_BG_COLOR, BRAND_PRIMARY_COLOR, BRAND_ACCENT_COLOR,
    BRAND_GLOW_COLOR, CHANNEL_NAME, SIGN_DATA, ZODIAC_SIGNS
)

W, H = 1280, 720
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


def _cx(draw, y, text, font, fill, off=4):
    w, _ = _tw(draw, text, font)
    x = (W - w) // 2
    draw.text((x + off, y + off), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


def _cosmic_bg_thumb(accent_color: tuple = None) -> Image.Image:
    """Deep space thumbnail background."""
    img  = Image.new("RGBA", (W, H), BRAND_BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    c1 = BRAND_BG_COLOR
    c2 = (18, 5, 50)
    for y in range(H):
        t = y / H
        r = int(c1[0]*(1-t) + c2[0]*t)
        g = int(c1[1]*(1-t) + c2[1]*t)
        b = int(c1[2]*(1-t) + c2[2]*t)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    import random
    rng = random.Random(99)
    for _ in range(350):
        sx  = rng.randint(0, W)
        sy  = rng.randint(0, H)
        bri = rng.randint(100, 255)
        sz  = rng.choice([1, 1, 1, 2, 2, 3])
        draw.ellipse([sx, sy, sx+sz, sy+sz], fill=(bri, bri, bri, bri))

    # Glow orbs
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od   = ImageDraw.Draw(over)
    glow = accent_color or BRAND_PRIMARY_COLOR
    for r_ in range(200, 0, -15):
        a = int(35 * (1 - r_/200))
        od.ellipse([W//2-r_, H//2-r_, W//2+r_, H//2+r_], fill=glow+(a,))
    img = Image.alpha_composite(img, over)

    # Dark vignette edges
    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd  = ImageDraw.Draw(vig)
    for i in range(120):
        a = int(180 * (i/120)**2)
        vd.rectangle([i, i, W-i, H-i], outline=(0, 0, 0, a), width=1)
    img = Image.alpha_composite(img, vig)

    return img.convert("RGB")


# ─────────────────────────────────────────────────────────────
# Thumbnail Type 1 — Weekly Omnibus
# ─────────────────────────────────────────────────────────────

def make_omnibus_thumbnail(week_label: str, major_transits: list) -> str:
    img  = _cosmic_bg_thumb()
    draw = ImageDraw.Draw(img)

    # Top banner
    draw.rectangle([0, 0, W, 70], fill=(0, 0, 0))
    bf = _font(28, bold=True)
    _cx(draw, 18, f"🔮  {CHANNEL_NAME.upper()}  |  WEEKLY COSMIC FORECAST", bf, BRAND_ACCENT_COLOR)

    # Main title
    tf = _font(100, bold=True)
    _cx(draw, 82, "WEEKLY", tf, BRAND_ACCENT_COLOR)
    tf2 = _font(100, bold=True)
    _cx(draw, 188, "HOROSCOPE", tf2, (255, 255, 255))

    # Week label
    wf = _font(42, bold=False)
    _cx(draw, 306, week_label, wf, (200, 180, 255))

    # Divider
    draw.line([(100, 360), (W-100, 360)], fill=(80, 60, 130), width=2)

    # Sign symbols in two rows
    syms = [SIGN_DATA[s]["symbol"] for s in ZODIAC_SIGNS]
    sf_  = _font(48, bold=True)
    row1 = "  ".join(syms[:6])
    row2 = "  ".join(syms[6:])
    _cx(draw, 375, row1, sf_, BRAND_GLOW_COLOR)
    _cx(draw, 440, row2, sf_, (160, 130, 220))

    # Major transit badge
    if major_transits:
        t   = major_transits[0]
        evt = t["event"][:45]
        pf  = _font(30, bold=True)
        pw, _ = _tw(draw, f"⚡ {evt}", pf)
        bx = (W - pw - 40) // 2
        draw.rounded_rectangle([bx, 510, bx+pw+40, 510+50], radius=25, fill=(150, 0, 0))
        draw.text((bx + 20, 518), f"⚡ {evt}", font=pf, fill=(255, 255, 255))

    # Bottom
    draw.rectangle([0, H-55, W, H], fill=(0, 0, 0))
    cf = _font(26, bold=True)
    _cx(draw, H-46, "👍 LIKE  |  🔔 SUBSCRIBE  |  💬 COMMENT YOUR SIGN", cf, BRAND_ACCENT_COLOR)

    out = ASTRO_THUMBNAIL
    img.save(out, quality=95)
    print(f"   📸 Omnibus thumbnail: {out}")
    return out


# ─────────────────────────────────────────────────────────────
# Thumbnail Type 2 — Per-Sign
# ─────────────────────────────────────────────────────────────

def make_sign_thumbnail(sign: str, week_label: str, key_insight: str = "") -> str:
    sd   = SIGN_DATA[sign]
    img  = _cosmic_bg_thumb(accent_color=sd["color"])
    draw = ImageDraw.Draw(img)

    # Top banner
    draw.rectangle([0, 0, W, 70], fill=(0, 0, 0))
    bf = _font(28, bold=True)
    _cx(draw, 18, f"🔮  {CHANNEL_NAME.upper()}  |  {sign.upper()} WEEKLY HOROSCOPE", bf, BRAND_ACCENT_COLOR)

    # Massive sign symbol — left side
    sym_f = _font(380, bold=True)
    sym   = sd["symbol"]
    sw, sh = _tw(draw, sym, sym_f)

    # Composite glow in a single pass: draw all glow ellipses onto one overlay
    # then alpha_composite once — avoids 60× redundant full-image composites.
    glow_over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_over)
    for gi in range(60, 0, -8):
        a = int(50 * (1 - gi / 60))
        glow_draw.ellipse(
            [40 - gi // 4, 100 - gi // 4,
             40 + sw + gi // 4, 100 + sh + gi // 4],
            fill=sd["color"] + (a,)
        )
    img = Image.alpha_composite(img.convert("RGBA"), glow_over).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw.text((42, 102), sym, font=sym_f, fill=(0, 0, 0))  # shadow
    draw.text((40, 100), sym, font=sym_f, fill=sd["color"])

    # Sign name — right side
    sn_f = _font(120, bold=True)
    snw, _ = _tw(draw, sign.upper(), sn_f)
    sx = W - snw - 40
    draw.text((sx + 4, 84), sign.upper(), font=sn_f, fill=(0, 0, 0))
    draw.text((sx, 80), sign.upper(), font=sn_f, fill=(255, 255, 255))

    # Dates + Element
    df = _font(34, bold=False)
    dw, _ = _tw(draw, sd["dates"], df)
    draw.text((W - dw - 44, 212), sd["dates"], font=df, fill=sd["color"])

    ef = _font(30, bold=False)
    ew, _ = _tw(draw, f"{sd['element']} Sign  |  ♟ {sd['planet']}", ef)
    draw.text((W - ew - 44, 256), f"{sd['element']} Sign  |  ♟ {sd['planet']}", font=ef, fill=(160, 140, 200))

    # Week label
    wf = _font(36, bold=True)
    ww, _ = _tw(draw, week_label, wf)
    draw.text((W - ww - 44, 310), week_label, font=wf, fill=BRAND_ACCENT_COLOR)

    # Divider
    draw.line([(W//2, 360), (W-40, 360)], fill=(80, 60, 120), width=1)

    # Key insight
    if key_insight:
        ki_text = key_insight[:60]
        kf = _font(28, bold=True)
        kw, _ = _tw(draw, ki_text, kf)
        kx = W - kw - 44
        draw.rounded_rectangle([kx - 12, 375, W - 28, 425], radius=14, fill=sd["color"])
        draw.text((kx, 382), ki_text, font=kf, fill=(255, 255, 255))

    # Life area icons
    icons_y = H - 140
    icons   = ["💕 Love", "💼 Career", "💰 Money", "🌿 Health"]
    ix = 80
    for ic in icons:
        if_ = _font(30, bold=True)
        draw.text((ix, icons_y), ic, font=if_, fill=(200, 180, 255))
        ix += _tw(draw, ic, if_)[0] + 40

    # Bottom strip
    draw.rectangle([0, H-55, W, H], fill=(0, 0, 0))
    cf = _font(26, bold=True)
    _cx(draw, H-46, "👍 LIKE  |  🔔 SUBSCRIBE  |  💬 COMMENT YOUR BIRTH DATE", cf, BRAND_ACCENT_COLOR)

    out = f"astro_thumb_{sign.lower()}.jpg"
    img.save(out, quality=95)
    print(f"   📸 {sign} thumbnail: {out}")
    return out


# ─────────────────────────────────────────────────────────────
# Thumbnail Type 3 — Transit Special
# ─────────────────────────────────────────────────────────────

def make_transit_thumbnail(transit: dict) -> str:
    event     = transit["event"]
    planet    = transit["planet"]
    date      = transit["date"]
    intensity = transit.get("intensity", "medium")

    glow = (200, 0, 0) if intensity == "high" else BRAND_PRIMARY_COLOR
    img  = _cosmic_bg_thumb(accent_color=glow)
    draw = ImageDraw.Draw(img)

    # Top banner
    draw.rectangle([0, 0, W, 70], fill=(0, 0, 0))
    bf = _font(28, bold=True)
    _cx(draw, 18, f"⚡  {CHANNEL_NAME.upper()}  |  COSMIC ALERT", bf, (255, 60, 60))

    # ALERT badge
    draw.rounded_rectangle([W-220, 80, W-20, 130], radius=20, fill=(200, 0, 0))
    af = _font(28, bold=True)
    draw.text((W-210, 90), "⚡ ALERT", font=af, fill=(255, 255, 255))

    # Planet name huge
    pf = _font(130, bold=True)
    _cx(draw, 80, planet.upper(), pf, BRAND_ACCENT_COLOR)

    # Event type
    ef = _font(68, bold=True)
    # Extract type from event
    ev_parts = event.replace(planet, "").strip()
    _cx(draw, 222, ev_parts.upper()[:35], ef, (255, 255, 255))

    # Date pill
    dp_f = _font(34, bold=True)
    dp   = f"📅  {date}"
    dpw, _ = _tw(draw, dp, dp_f)
    dpx    = (W - dpw - 40) // 2
    draw.rounded_rectangle([dpx, 308, dpx+dpw+40, 352], radius=20, fill=(0, 0, 0))
    draw.text((dpx+20, 316), dp, font=dp_f, fill=BRAND_ACCENT_COLOR)

    # Affected signs
    af_signs = transit.get("affected_signs", [])
    if af_signs:
        sf_ = _font(38, bold=True)
        sl  = "  ".join([SIGN_DATA[s]["symbol"] for s in af_signs[:6]])
        _cx(draw, 380, sl, sf_, BRAND_GLOW_COLOR)
        lf2 = _font(26, bold=False)
        _cx(draw, 430, "Most Affected Signs", lf2, (160, 140, 200))

    # Urgency text
    uf = _font(40, bold=True)
    _cx(draw, 490, "HOW YOUR SIGN IS AFFECTED  ⬇️", uf, BRAND_ACCENT_COLOR)

    # Bottom
    draw.rectangle([0, H-140, W, H-55], fill=(80, 0, 0))
    cf = _font(30, bold=True)
    _cx(draw, H-132, "EVERY SIGN EXPLAINED — WATCH NOW", cf, (255, 255, 255))
    draw.rectangle([0, H-55, W, H], fill=(0, 0, 0))
    cf2 = _font(26, bold=True)
    _cx(draw, H-46, "👍 LIKE  |  🔔 SUBSCRIBE  |  💬 WHICH SIGN ARE YOU?", cf2, BRAND_ACCENT_COLOR)

    out = f"astro_thumb_transit_{planet.lower()}.jpg"
    img.save(out, quality=95)
    print(f"   📸 Transit thumbnail: {out}")
    return out
